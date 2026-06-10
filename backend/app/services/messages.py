import logging
from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import ChannelType, PaginationOptions, RepositoryPage
from app.db.models.queries import MessageFilters, SortOptions
from app.db.models.records import MessageCreate, MessageRead
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.schemas.messages import MessageCreateRequest
from app.services.base import BaseService
from app.services.organization_access import OrganizationAccessService, TenantContext


logger = logging.getLogger(__name__)

CRM_WRITE_ROLES = {"agent", "manager", "admin", "owner"}


class MessageService(BaseService):
    def __init__(self, supabase_factory: SupabaseClientFactory | None = None) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        service_client = self.supabase_factory.get_service_client()
        self.repository = MessageRepository(service_client)
        self.conversation_repository = ConversationRepository(service_client)
        self.organization_access_service = OrganizationAccessService(self.supabase_factory)

    async def create(self, tenant: TenantContext, payload: MessageCreateRequest) -> MessageRead:
        self._require_role(tenant, CRM_WRITE_ROLES)
        context = self._repository_context(tenant)
        existing = self._find_existing_by_external_keys(context, payload)
        if existing is not None:
            return existing

        conversation = self.conversation_repository.get_by_id(context, payload.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        if payload.customer_id is not None and payload.customer_id != conversation.customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message customer_id does not match conversation customer_id",
            )

        message_data = payload.model_dump(mode="python", exclude_unset=True)
        message_data["customer_id"] = payload.customer_id or conversation.customer_id
        message_data["generated_by_ai"] = payload.sender_type == "ai"
        message_data["sent_by_human"] = payload.sender_type == "human"
        message_payload = MessageCreate(**message_data)
        try:
            message = self.repository.create(context, message_payload)
        except Exception as exc:
            existing_after_conflict = self._find_existing_by_external_keys(context, payload)
            if existing_after_conflict is not None:
                return existing_after_conflict
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Message creation failed. Please try again.",
            ) from exc

        # TODO: Move message creation + conversation last-message update into DB RPC/transaction before production.
        try:
            self.conversation_repository.update_last_message(
                context,
                conversation.id,
                last_message_id=message.id,
                last_message_at=message.created_at,
            )
        except Exception:
            logger.warning(
                "Failed to update conversation last-message fields",
                extra={
                    "organization_id": str(tenant.organization_id),
                    "conversation_id": str(conversation.id),
                    "message_id": str(message.id),
                },
                exc_info=True,
            )
        return message

    async def list_by_conversation(
        self,
        tenant: TenantContext,
        conversation_id: UUID,
        filters: MessageFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[MessageRead]:
        context = self._repository_context(tenant)
        if self.conversation_repository.get_by_id(context, conversation_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return self.repository.list_by_conversation(
            context,
            conversation_id=conversation_id,
            filters=filters,
            pagination=pagination,
            sort=sort,
        )

    async def get_by_external_message_id(
        self,
        tenant: TenantContext,
        external_message_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead:
        message = self.repository.get_by_external_message_id(
            self._repository_context(tenant),
            external_message_id=external_message_id,
            channel=channel,
        )
        return self._require_message(message)

    async def get_by_external_event_id(
        self,
        tenant: TenantContext,
        external_event_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead:
        message = self.repository.get_by_external_event_id(
            self._repository_context(tenant),
            external_event_id=external_event_id,
            channel=channel,
        )
        return self._require_message(message)

    async def get_by_webhook_delivery_id(
        self,
        tenant: TenantContext,
        webhook_delivery_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead:
        message = self.repository.get_by_webhook_delivery_id(
            self._repository_context(tenant),
            webhook_delivery_id=webhook_delivery_id,
            channel=channel,
        )
        return self._require_message(message)

    def _find_existing_by_external_keys(
        self,
        context: OrganizationContext,
        payload: MessageCreateRequest,
    ) -> MessageRead | None:
        if payload.external_message_id is not None:
            message = self.repository.get_by_external_message_id(
                context,
                external_message_id=payload.external_message_id,
                channel=payload.channel,
            )
            if message is not None:
                return message

        if payload.external_event_id is not None:
            message = self.repository.get_by_external_event_id(
                context,
                external_event_id=payload.external_event_id,
                channel=payload.channel,
            )
            if message is not None:
                return message

        if payload.webhook_delivery_id is not None:
            message = self.repository.get_by_webhook_delivery_id(
                context,
                webhook_delivery_id=payload.webhook_delivery_id,
                channel=payload.channel,
            )
            if message is not None:
                return message

        return None

    def _require_message(self, message: MessageRead | None) -> MessageRead:
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found",
            )
        return message

    def _require_role(self, tenant: TenantContext, allowed_roles: set[str]) -> None:
        self.organization_access_service.require_role(
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            allowed_roles=allowed_roles,
        )

    def _repository_context(self, tenant: TenantContext) -> OrganizationContext:
        return OrganizationContext(
            organization_id=tenant.organization_id,
            user_id=tenant.user_id,
            membership_id=tenant.membership_id,
            role=tenant.role,
        )

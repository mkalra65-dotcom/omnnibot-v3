from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import PaginationOptions, RepositoryPage
from app.db.models.queries import ConversationFilters, SortOptions
from app.db.models.records import ConversationCreate, ConversationRead
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.customer_repository import CustomerRepository
from app.schemas.conversations import ConversationCreateRequest, FollowupTimestampsUpdate
from app.services.base import BaseService
from app.services.organization_access import OrganizationAccessService, TenantContext


CRM_WRITE_ROLES = {"agent", "manager", "admin", "owner"}
CRM_PRIVILEGED_ROLES = {"manager", "admin", "owner"}


class ConversationService(BaseService):
    def __init__(self, supabase_factory: SupabaseClientFactory | None = None) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        service_client = self.supabase_factory.get_service_client()
        self.repository = ConversationRepository(service_client)
        self.customer_repository = CustomerRepository(service_client)
        self.organization_access_service = OrganizationAccessService(self.supabase_factory)

    async def create(self, tenant: TenantContext, payload: ConversationCreateRequest) -> ConversationRead:
        self._require_role(tenant, CRM_WRITE_ROLES)
        context = self._repository_context(tenant)
        if self.customer_repository.get_by_id(context, payload.customer_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )
        return self.repository.create(
            context,
            ConversationCreate(**payload.model_dump(mode="python", exclude_unset=True)),
        )

    async def list(
        self,
        tenant: TenantContext,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        return self.repository.list_by_organization(
            self._repository_context(tenant),
            filters=filters,
            pagination=pagination,
            sort=sort,
        )

    async def get(self, tenant: TenantContext, conversation_id: UUID) -> ConversationRead:
        conversation = self.repository.get_by_id(self._repository_context(tenant), conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

    async def list_by_customer(
        self,
        tenant: TenantContext,
        customer_id: UUID,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        context = self._repository_context(tenant)
        if self.customer_repository.get_by_id(context, customer_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )
        return self.repository.list_by_customer(
            context,
            customer_id=customer_id,
            filters=filters,
            pagination=pagination,
            sort=sort,
        )

    async def update_handoff_status(
        self,
        tenant: TenantContext,
        conversation_id: UUID,
        handoff_status: str,
    ) -> ConversationRead:
        self._require_role(tenant, CRM_PRIVILEGED_ROLES)
        conversation = self.repository.update_handoff_status(
            self._repository_context(tenant),
            conversation_id,
            handoff_status,
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

    async def update_followup_timestamps(
        self,
        tenant: TenantContext,
        conversation_id: UUID,
        payload: FollowupTimestampsUpdate,
    ) -> ConversationRead:
        self._require_role(tenant, CRM_PRIVILEGED_ROLES)
        conversation = self.repository.update_followup_timestamps(
            self._repository_context(tenant),
            conversation_id,
            payload,
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

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

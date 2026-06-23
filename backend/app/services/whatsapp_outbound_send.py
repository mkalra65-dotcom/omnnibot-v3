from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import ChannelType, MessageStatus, PaginationOptions, WhatsAppAccountStatus
from app.db.models.queries import WhatsAppAccountFilters
from app.db.models.records import AiDraftReviewRead, AiDraftReviewUpdate, MessageCreate
from app.db.repositories.ai_draft_review_repository import AiDraftReviewRepository
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.customer_repository import CustomerRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.whatsapp_account_repository import WhatsAppAccountRepository
from app.schemas.whatsapp_outbound import WhatsAppReviewSendResponse
from app.services.base import BaseService
from app.services.organization_access import OrganizationAccessService, TenantContext
from app.services.secrets import SecretResolutionError, SecretResolver
from app.services.whatsapp_outbound_provider import (
    WhatsAppOutboundProvider,
    WhatsAppOutboundProviderError,
    WhatsAppOutboundProviderTimeout,
    WhatsAppOutboundSendRequest,
)


WHATSAPP_SEND_ROLES = {"agent", "manager", "admin", "owner"}
SENDABLE_REVIEW_STATUSES = {"approved", "edited"}


@dataclass(frozen=True, slots=True)
class WhatsAppOutboundSendServiceResult:
    review_id: UUID
    message_id: UUID | None
    external_message_id: str | None
    status: str
    sent_at: datetime | None
    idempotent: bool = False

    def as_response(self) -> WhatsAppReviewSendResponse:
        return WhatsAppReviewSendResponse(
            review_id=self.review_id,
            message_id=self.message_id,
            external_message_id=self.external_message_id,
            status=self.status,
            sent_at=self.sent_at,
            idempotent=self.idempotent,
        )


class WhatsAppOutboundSendService(BaseService):
    def __init__(
        self,
        *,
        review_repository: AiDraftReviewRepository | Any | None = None,
        message_repository: MessageRepository | Any | None = None,
        conversation_repository: ConversationRepository | Any | None = None,
        customer_repository: CustomerRepository | Any | None = None,
        whatsapp_account_repository: WhatsAppAccountRepository | Any | None = None,
        organization_access_service: OrganizationAccessService | Any | None = None,
        secret_resolver: SecretResolver | Any | None = None,
        provider: WhatsAppOutboundProvider | Any | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        service_client = None
        if (
            review_repository is None
            or message_repository is None
            or conversation_repository is None
            or customer_repository is None
            or whatsapp_account_repository is None
        ):
            service_client = self.supabase_factory.get_service_client()
        self.review_repository = review_repository or AiDraftReviewRepository(service_client)
        self.message_repository = message_repository or MessageRepository(service_client)
        self.conversation_repository = conversation_repository or ConversationRepository(service_client)
        self.customer_repository = customer_repository or CustomerRepository(service_client)
        self.whatsapp_account_repository = whatsapp_account_repository or WhatsAppAccountRepository(service_client)
        self.organization_access_service = organization_access_service or OrganizationAccessService(
            self.supabase_factory
        )
        self.secret_resolver = secret_resolver or SecretResolver()
        if provider is None:
            from app.services.whatsapp_outbound_provider import MetaWhatsAppOutboundProvider

            provider = MetaWhatsAppOutboundProvider()
        self.provider = provider

    def send_review(
        self,
        tenant: TenantContext,
        review_id: UUID,
        *,
        send_idempotency_key: str,
    ) -> WhatsAppOutboundSendServiceResult:
        self._require_non_blank(send_idempotency_key, "send_idempotency_key")
        self._require_role(tenant)
        context = self._context(tenant)

        existing_by_key = self.review_repository.get_by_send_idempotency_key(
            context,
            send_idempotency_key,
        )
        if existing_by_key is not None:
            return self._existing_idempotency_result(context, existing_by_key)

        review = self._require_review(context, review_id)
        if review.status == "sent":
            return self._existing_sent_result(context, review, idempotent=True)
        if review.status not in SENDABLE_REVIEW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="AI draft review is not approved for sending",
            )

        conversation = self.conversation_repository.get_by_id(context, review.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if conversation.channel != ChannelType.WHATSAPP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review conversation is not a WhatsApp conversation",
            )

        customer_id = review.customer_id or conversation.customer_id
        to_wa_id = self._resolve_customer_wa_id(context, customer_id)
        account = self._resolve_active_account(context)

        claimed = self.review_repository.claim_for_send(
            context,
            review_id,
            send_idempotency_key,
        )
        if claimed is None:
            return self._handle_claim_miss(context, review_id, send_idempotency_key)

        final_text = self._final_text(claimed)
        queued_message = self.message_repository.create(
            context,
            MessageCreate(
                conversation_id=claimed.conversation_id,
                customer_id=customer_id,
                channel=ChannelType.WHATSAPP,
                direction="outbound",
                sender_type="human",
                sender_user_id=tenant.user_id,
                message_type="text",
                body=final_text,
                status=MessageStatus.QUEUED,
                generated_by_ai=False,
                sent_by_human=True,
                provider_payload={},
                metadata={
                    "ai_assisted": True,
                    "ai_draft_review_id": str(claimed.id),
                    "send_idempotency_key": send_idempotency_key,
                    "phone_number_id": account.phone_number_id,
                },
            ),
        )
        self.review_repository.update(
            context,
            claimed.id,
            AiDraftReviewUpdate(
                sent_message_id=queued_message.id,
                send_error_code=None,
                send_error_message=None,
            ),
        )

        try:
            token = self.secret_resolver.resolve(account.access_token_secret_ref or "")
        except SecretResolutionError as exc:
            self._mark_known_failure(
                context,
                review_id=claimed.id,
                message_id=queued_message.id,
                code="missing_whatsapp_access_token",
                message="WhatsApp access token is not configured",
            )
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="WhatsApp access token is not configured",
            ) from exc

        try:
            provider_result = self.provider.send_text(
                WhatsAppOutboundSendRequest(
                    phone_number_id=account.phone_number_id,
                    access_token=token,
                    to_wa_id=to_wa_id,
                    body=final_text,
                )
            )
        except WhatsAppOutboundProviderTimeout as exc:
            self.review_repository.update(
                context,
                claimed.id,
                AiDraftReviewUpdate(
                    send_error_code=exc.code,
                    send_error_message=exc.message,
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="WhatsApp send outcome is unknown; not retrying automatically",
            ) from exc
        except WhatsAppOutboundProviderError as exc:
            self._mark_known_failure(
                context,
                review_id=claimed.id,
                message_id=queued_message.id,
                code=exc.code,
                message=exc.message,
                provider_response=exc.response_payload,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Meta WhatsApp send failed",
            ) from exc

        sent_at = self._now()
        sent_message = self.message_repository.update(
            context,
            queued_message.id,
            {
                "external_message_id": provider_result.external_message_id,
                "status": MessageStatus.SENT,
                "sent_at": sent_at,
                "provider_payload": provider_result.provider_response,
            },
        )
        sent_review = self.review_repository.update(
            context,
            claimed.id,
            AiDraftReviewUpdate(
                status="sent",
                sent_message_id=queued_message.id,
                sent_by_membership_id=tenant.membership_id,
                sent_at=sent_at,
                provider_response=provider_result.provider_response,
                send_error_code=None,
                send_error_message=None,
            ),
        )
        self.conversation_repository.update_last_message(
            context,
            claimed.conversation_id,
            last_message_id=queued_message.id,
            last_message_at=sent_at,
        )

        return WhatsAppOutboundSendServiceResult(
            review_id=claimed.id,
            message_id=queued_message.id,
            external_message_id=provider_result.external_message_id,
            status=sent_review.status if sent_review else "sent",
            sent_at=sent_message.sent_at if sent_message else sent_at,
        )

    def _existing_idempotency_result(
        self,
        context: OrganizationContext,
        review: AiDraftReviewRead,
    ) -> WhatsAppOutboundSendServiceResult:
        if review.status == "sent":
            return self._existing_sent_result(context, review, idempotent=True)
        if review.send_error_code == "meta_timeout":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Previous WhatsApp send outcome is unknown; not retrying automatically",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Send idempotency key is already in use",
        )

    def _existing_sent_result(
        self,
        context: OrganizationContext,
        review: AiDraftReviewRead,
        *,
        idempotent: bool,
    ) -> WhatsAppOutboundSendServiceResult:
        message = (
            self.message_repository.get_by_id(context, review.sent_message_id)
            if review.sent_message_id is not None
            else None
        )
        return WhatsAppOutboundSendServiceResult(
            review_id=review.id,
            message_id=review.sent_message_id,
            external_message_id=message.external_message_id if message else None,
            status=review.status,
            sent_at=review.sent_at,
            idempotent=idempotent,
        )

    def _handle_claim_miss(
        self,
        context: OrganizationContext,
        review_id: UUID,
        send_idempotency_key: str,
    ) -> WhatsAppOutboundSendServiceResult:
        existing_by_key = self.review_repository.get_by_send_idempotency_key(context, send_idempotency_key)
        if existing_by_key is not None:
            return self._existing_idempotency_result(context, existing_by_key)

        review = self._require_review(context, review_id)
        if review.status == "sent":
            return self._existing_sent_result(context, review, idempotent=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI draft review send was already claimed")

    def _mark_known_failure(
        self,
        context: OrganizationContext,
        *,
        review_id: UUID,
        message_id: UUID,
        code: str,
        message: str,
        provider_response: dict[str, Any] | None = None,
    ) -> None:
        failed_at = self._now()
        self.message_repository.update(
            context,
            message_id,
            {
                "status": MessageStatus.FAILED,
                "failed_at": failed_at,
                "provider_payload": provider_response or {},
            },
        )
        self.review_repository.update(
            context,
            review_id,
            AiDraftReviewUpdate(
                send_error_code=code,
                send_error_message=message,
                provider_response=provider_response or {},
            ),
        )

    def _resolve_active_account(self, context: OrganizationContext):
        accounts = self.whatsapp_account_repository.list_by_organization(
            context,
            filters=WhatsAppAccountFilters(status=WhatsAppAccountStatus.ACTIVE),
            pagination=PaginationOptions(page=1, page_size=2),
        ).items
        if len(accounts) != 1:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Active WhatsApp account did not resolve uniquely",
            )
        return accounts[0]

    def _resolve_customer_wa_id(self, context: OrganizationContext, customer_id: UUID) -> str:
        identities = [
            identity
            for identity in self.customer_repository.list_identities_for_customer(context, customer_id)
            if identity.provider == "whatsapp"
        ]
        if len(identities) != 1:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="WhatsApp customer identity did not resolve uniquely",
            )
        wa_id = identities[0].provider_user_id or identities[0].provider_phone
        if wa_id is None or not wa_id.strip():
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="WhatsApp customer identity is missing recipient id",
            )
        return wa_id.strip()

    def _final_text(self, review: AiDraftReviewRead) -> str:
        if review.status == "edited":
            if review.edited_text is None or not review.edited_text.strip():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Edited review has no final text")
            return review.edited_text
        return review.draft_text

    def _require_role(self, tenant: TenantContext) -> None:
        self.organization_access_service.require_role(
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            allowed_roles=WHATSAPP_SEND_ROLES,
        )

    def _require_review(self, context: OrganizationContext, review_id: UUID) -> AiDraftReviewRead:
        review = self.review_repository.get_by_id(context, review_id)
        if review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI draft review not found")
        return review

    def _context(self, tenant: TenantContext) -> OrganizationContext:
        return OrganizationContext(
            organization_id=tenant.organization_id,
            user_id=tenant.user_id,
            membership_id=tenant.membership_id,
            role=tenant.role,
        )

    def _require_non_blank(self, value: str, field_name: str) -> None:
        if not value.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must not be blank")

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

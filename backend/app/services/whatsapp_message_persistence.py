from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from postgrest.exceptions import APIError

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import ChannelType
from app.db.models.records import MessageCreate, MessageRead
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.services.whatsapp_conversation_resolution import WhatsAppConversationResolution
from app.services.whatsapp_customer_identity_resolution import WhatsAppCustomerIdentityResolution
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolution
from app.services.whatsapp_payloads import MetaWhatsAppInboundMessage, MetaWhatsAppWebhookPayload


logger = logging.getLogger(__name__)

SUPPORTED_MESSAGE_TYPES = {"text", "image", "document", "audio"}


@dataclass(frozen=True, slots=True)
class WhatsAppMessagePersistenceResult:
    persisted: bool
    duplicate: bool = False
    skipped_reason: str | None = None
    message_id: UUID | None = None


class WhatsAppMessagePersistenceService:
    def __init__(
        self,
        message_repository: MessageRepository | None = None,
        conversation_repository: ConversationRepository | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self._message_repository = message_repository
        self._conversation_repository = conversation_repository
        self._supabase_factory = supabase_factory

    def persist_inbound(
        self,
        *,
        payload: MetaWhatsAppWebhookPayload,
        organization_resolution: WhatsAppOrganizationResolution,
        customer_identity_resolution: WhatsAppCustomerIdentityResolution | None,
        conversation_resolution: WhatsAppConversationResolution | None,
        webhook_delivery_id: str | None,
    ) -> list[WhatsAppMessagePersistenceResult]:
        if organization_resolution.organization_id is None:
            return [WhatsAppMessagePersistenceResult(persisted=False, skipped_reason="missing_organization_id")]
        if customer_identity_resolution is None or customer_identity_resolution.customer_id is None:
            return [WhatsAppMessagePersistenceResult(persisted=False, skipped_reason="missing_customer_id")]
        if conversation_resolution is None or conversation_resolution.conversation_id is None:
            return [WhatsAppMessagePersistenceResult(persisted=False, skipped_reason="missing_conversation_id")]
        if not payload.inbound_messages:
            return [WhatsAppMessagePersistenceResult(persisted=False, skipped_reason="missing_inbound_message")]

        results: list[WhatsAppMessagePersistenceResult] = []
        for inbound_message in payload.inbound_messages:
            results.append(
                self._persist_one(
                    payload=payload,
                    organization_id=organization_resolution.organization_id,
                    customer_id=customer_identity_resolution.customer_id,
                    conversation_id=conversation_resolution.conversation_id,
                    webhook_delivery_id=webhook_delivery_id,
                    inbound_message=inbound_message,
                )
            )
        return results

    def _persist_one(
        self,
        *,
        payload: MetaWhatsAppWebhookPayload,
        organization_id: UUID,
        customer_id: UUID,
        conversation_id: UUID,
        webhook_delivery_id: str | None,
        inbound_message: MetaWhatsAppInboundMessage,
    ) -> WhatsAppMessagePersistenceResult:
        if inbound_message.external_message_id is None:
            return WhatsAppMessagePersistenceResult(
                persisted=False,
                skipped_reason="missing_external_message_id",
            )

        context = OrganizationContext(organization_id=organization_id)
        existing = self.message_repository.get_by_external_message_id(
            context,
            external_message_id=inbound_message.external_message_id,
            channel=ChannelType.WHATSAPP,
        )
        if existing is not None:
            return WhatsAppMessagePersistenceResult(
                persisted=True,
                duplicate=True,
                message_id=existing.id,
            )

        message_payload = MessageCreate(
            conversation_id=conversation_id,
            customer_id=customer_id,
            channel=ChannelType.WHATSAPP,
            direction="inbound",
            sender_type="customer",
            external_message_id=inbound_message.external_message_id,
            external_event_id=self._safe_external_event_id(payload, inbound_message),
            webhook_delivery_id=None,
            message_type=inbound_message.message_type or "unsupported",
            body=inbound_message.body if inbound_message.message_type == "text" else None,
            provider_payload={},
            metadata=self._message_metadata(payload, inbound_message, webhook_delivery_id),
            external_created_at=inbound_message.external_created_at,
        )
        try:
            message = self.message_repository.create(context, message_payload)
        except APIError as exc:
            if _is_unique_violation(exc):
                existing_after_conflict = self.message_repository.get_by_external_message_id(
                    context,
                    external_message_id=inbound_message.external_message_id,
                    channel=ChannelType.WHATSAPP,
                )
                if existing_after_conflict is not None:
                    return WhatsAppMessagePersistenceResult(
                        persisted=True,
                        duplicate=True,
                        message_id=existing_after_conflict.id,
                    )
            if inbound_message.message_type not in SUPPORTED_MESSAGE_TYPES:
                logger.warning(
                    "Skipped unsupported WhatsApp message after message insert failed",
                    extra={
                        "organization_id": str(organization_id),
                        "conversation_id": str(conversation_id),
                        "external_message_id": inbound_message.external_message_id,
                        "message_type": inbound_message.message_type,
                    },
                    exc_info=True,
                )
                return WhatsAppMessagePersistenceResult(
                    persisted=False,
                    skipped_reason="unsupported_message_type_not_persisted",
                )
            raise

        try:
            self.conversation_repository.update_last_message(
                context,
                conversation_id,
                last_message_id=message.id,
                last_message_at=message.created_at or message.external_created_at,
            )
        except Exception:
            logger.warning(
                "Failed to update WhatsApp conversation last-message fields",
                extra={
                    "organization_id": str(organization_id),
                    "conversation_id": str(conversation_id),
                    "message_id": str(message.id),
                },
                exc_info=True,
            )

        return WhatsAppMessagePersistenceResult(persisted=True, message_id=message.id)

    def _message_metadata(
        self,
        payload: MetaWhatsAppWebhookPayload,
        inbound_message: MetaWhatsAppInboundMessage,
        webhook_delivery_id: str | None,
    ) -> dict:
        metadata = {
            **inbound_message.metadata,
            "phone_number_id": payload.phone_number_id,
            "whatsapp_business_account_id": payload.whatsapp_business_account_id,
            "webhook_delivery_id": webhook_delivery_id,
        }
        if inbound_message.message_type not in SUPPORTED_MESSAGE_TYPES:
            metadata["unsupported_message_type"] = inbound_message.message_type
        return {key: value for key, value in metadata.items() if value is not None}

    def _safe_external_event_id(
        self,
        payload: MetaWhatsAppWebhookPayload,
        inbound_message: MetaWhatsAppInboundMessage,
    ) -> str | None:
        if payload.external_event_id == inbound_message.external_message_id:
            return payload.external_event_id
        return None

    @property
    def message_repository(self) -> MessageRepository:
        if self._message_repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._message_repository = MessageRepository(factory.get_service_client())
        return self._message_repository

    @property
    def conversation_repository(self) -> ConversationRepository:
        if self._conversation_repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._conversation_repository = ConversationRepository(factory.get_service_client())
        return self._conversation_repository


def _is_unique_violation(exc: APIError) -> bool:
    return exc.json().get("code") == "23505"

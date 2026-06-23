from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import ChannelType, MessageStatus
from app.db.models.records import MessageRead
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.message_repository import MessageRepository
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolution
from app.services.whatsapp_payloads import MetaWhatsAppStatusEvent


STATUS_MAPPING = {
    "sent": MessageStatus.SENT,
    "delivered": MessageStatus.DELIVERED,
    "read": MessageStatus.READ,
    "failed": MessageStatus.FAILED,
}


@dataclass(frozen=True, slots=True)
class WhatsAppStatusUpdateResult:
    external_message_id: str | None
    provider_status: str | None
    updated: bool
    skipped_reason: str | None = None


class WhatsAppStatusUpdateService:
    def __init__(
        self,
        *,
        message_repository: MessageRepository | Any | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self._message_repository = message_repository
        self._supabase_factory = supabase_factory

    def process_status_events(
        self,
        *,
        status_events: tuple[MetaWhatsAppStatusEvent, ...],
        organization_resolution: WhatsAppOrganizationResolution,
    ) -> list[WhatsAppStatusUpdateResult]:
        context = OrganizationContext(organization_id=organization_resolution.organization_id)
        return [
            self.process_status_event(status_event=event, context=context)
            for event in status_events
        ]

    def process_status_event(
        self,
        *,
        status_event: MetaWhatsAppStatusEvent,
        context: OrganizationContext,
    ) -> WhatsAppStatusUpdateResult:
        mapped_status = STATUS_MAPPING.get(status_event.status or "")
        if mapped_status is None:
            return WhatsAppStatusUpdateResult(
                external_message_id=status_event.external_message_id,
                provider_status=status_event.status,
                updated=False,
                skipped_reason="unknown_status",
            )
        if status_event.external_message_id is None:
            return WhatsAppStatusUpdateResult(
                external_message_id=None,
                provider_status=status_event.status,
                updated=False,
                skipped_reason="missing_external_message_id",
            )

        message = self.message_repository.get_by_external_message_id(
            context,
            external_message_id=status_event.external_message_id,
            channel=ChannelType.WHATSAPP,
            direction="outbound",
        )
        if message is None:
            return WhatsAppStatusUpdateResult(
                external_message_id=status_event.external_message_id,
                provider_status=status_event.status,
                updated=False,
                skipped_reason="message_not_found",
            )

        update_payload = self._build_update_payload(message, mapped_status, status_event)
        self.message_repository.update(context, message.id, update_payload)
        return WhatsAppStatusUpdateResult(
            external_message_id=status_event.external_message_id,
            provider_status=status_event.status,
            updated=True,
        )

    def _build_update_payload(
        self,
        message: MessageRead,
        mapped_status: MessageStatus,
        status_event: MetaWhatsAppStatusEvent,
    ) -> dict[str, Any]:
        event_at = status_event.event_at
        payload: dict[str, Any] = {
            "provider_payload": self._provider_payload(message, status_event),
        }

        if mapped_status == MessageStatus.SENT:
            if message.sent_at is None:
                payload["sent_at"] = event_at
            if message.status not in {MessageStatus.DELIVERED, MessageStatus.READ}:
                payload["status"] = MessageStatus.SENT
            return payload

        if mapped_status == MessageStatus.DELIVERED:
            if message.delivered_at is None:
                payload["delivered_at"] = event_at
            if message.status != MessageStatus.READ:
                payload["status"] = MessageStatus.DELIVERED
            return payload

        if mapped_status == MessageStatus.READ:
            if message.delivered_at is None:
                payload["delivered_at"] = event_at
            if message.read_at is None:
                payload["read_at"] = event_at
            payload["status"] = MessageStatus.READ
            return payload

        if mapped_status == MessageStatus.FAILED:
            if message.failed_at is None:
                payload["failed_at"] = event_at
            if message.status != MessageStatus.READ:
                payload["status"] = MessageStatus.FAILED
            return payload

        return payload

    def _provider_payload(
        self,
        message: MessageRead,
        status_event: MetaWhatsAppStatusEvent,
    ) -> dict[str, Any]:
        provider_payload = dict(message.provider_payload or {})
        provider_payload["last_status_event"] = {
            key: value
            for key, value in {
                "provider": "whatsapp",
                "source": "meta",
                "external_message_id": status_event.external_message_id,
                "status": status_event.status,
                "event_at": self._serialize_datetime(status_event.event_at),
                "recipient_id": status_event.recipient_id,
                "metadata": status_event.metadata,
            }.items()
            if value is not None
        }
        return provider_payload

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @property
    def message_repository(self):
        if self._message_repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._message_repository = MessageRepository(factory.get_service_client())
        return self._message_repository

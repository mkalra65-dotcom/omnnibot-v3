from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.db.models.common import ChannelType, MessageStatus
from app.db.models.records import MessageRead
from app.db.repositories.base_repository import OrganizationContext
from app.services.whatsapp_payloads import MetaWhatsAppStatusEvent
from app.services.whatsapp_status_updates import WhatsAppStatusUpdateService


ORG_A = UUID("10000000-0000-0000-0000-000000000001")
ORG_B = UUID("20000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("30000000-0000-0000-0000-000000000001")
CUSTOMER_ID = UUID("40000000-0000-0000-0000-000000000001")
EVENT_AT = datetime(2026, 6, 24, 10, 30, tzinfo=timezone.utc)


def test_sent_status_updates_message_to_sent() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.QUEUED)])
    service = _service(repository)

    result = service.process_status_event(
        status_event=_status_event("sent"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    message = repository.messages[0]
    assert result.updated is True
    assert message.status == MessageStatus.SENT
    assert message.sent_at == EVENT_AT
    assert message.provider_payload["last_status_event"]["status"] == "sent"


def test_delivered_updates_delivered_at() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.SENT)])
    service = _service(repository)

    service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    message = repository.messages[0]
    assert message.status == MessageStatus.DELIVERED
    assert message.delivered_at == EVENT_AT


def test_read_updates_read_at_and_does_not_downgrade() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.READ, delivered_at=None)])
    service = _service(repository)

    service.process_status_event(
        status_event=_status_event("read"),
        context=OrganizationContext(organization_id=ORG_A),
    )
    service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )
    service.process_status_event(
        status_event=_status_event("sent"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    message = repository.messages[0]
    assert message.status == MessageStatus.READ
    assert message.delivered_at == EVENT_AT
    assert message.read_at == EVENT_AT


def test_failed_updates_failed_at() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.SENT)])
    service = _service(repository)

    service.process_status_event(
        status_event=_status_event("failed"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    message = repository.messages[0]
    assert message.status == MessageStatus.FAILED
    assert message.failed_at == EVENT_AT


def test_failed_does_not_override_already_read_status() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.READ)])
    service = _service(repository)

    service.process_status_event(
        status_event=_status_event("failed"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    message = repository.messages[0]
    assert message.status == MessageStatus.READ
    assert message.failed_at == EVENT_AT


def test_repeated_status_event_is_idempotent() -> None:
    first_delivered_at = datetime(2026, 6, 24, 9, 0, tzinfo=timezone.utc)
    repository = FakeMessageRepository(
        [_message(status=MessageStatus.DELIVERED, delivered_at=first_delivered_at)]
    )
    service = _service(repository)

    service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    assert repository.messages[0].delivered_at == first_delivered_at
    assert len(repository.updates) == 1


def test_unknown_status_is_accepted_without_crash() -> None:
    repository = FakeMessageRepository([_message(status=MessageStatus.SENT)])
    service = _service(repository)

    result = service.process_status_event(
        status_event=_status_event("played"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    assert result.updated is False
    assert result.skipped_reason == "unknown_status"
    assert repository.updates == []


def test_status_event_for_missing_message_is_accepted_without_crash() -> None:
    repository = FakeMessageRepository([])
    service = _service(repository)

    result = service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    assert result.updated is False
    assert result.skipped_reason == "message_not_found"
    assert repository.updates == []


def test_cross_org_status_cannot_update_another_org_message() -> None:
    repository = FakeMessageRepository([_message(organization_id=ORG_B, status=MessageStatus.SENT)])
    service = _service(repository)

    result = service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    assert result.updated is False
    assert result.skipped_reason == "message_not_found"
    assert repository.messages[0].status == MessageStatus.SENT
    assert repository.messages[0].delivered_at is None


def test_inbound_message_with_same_external_id_is_not_updated() -> None:
    repository = FakeMessageRepository(
        [_message(status=MessageStatus.RECEIVED, direction="inbound", sender_type="customer")]
    )
    service = _service(repository)

    result = service.process_status_event(
        status_event=_status_event("delivered"),
        context=OrganizationContext(organization_id=ORG_A),
    )

    assert result.updated is False
    assert result.skipped_reason == "message_not_found"
    assert repository.messages[0].status == MessageStatus.RECEIVED
    assert repository.messages[0].delivered_at is None
    assert repository.updates == []


class FakeMessageRepository:
    def __init__(self, messages: list[MessageRead]) -> None:
        self.messages = messages
        self.updates: list[dict] = []

    def get_by_external_message_id(
        self,
        organization_id,
        external_message_id,
        channel=None,
        direction=None,
    ):
        org_id = _org_id(organization_id)
        return next(
            (
                message
                for message in self.messages
                if message.organization_id == org_id
                and message.external_message_id == external_message_id
                and (channel is None or message.channel == channel)
                and (direction is None or message.direction == direction)
            ),
            None,
        )

    def update(self, organization_id, record_id, payload):
        org_id = _org_id(organization_id)
        for index, message in enumerate(self.messages):
            if message.organization_id == org_id and message.id == record_id:
                self.updates.append(payload)
                self.messages[index] = message.model_copy(update=payload)
                return self.messages[index]
        return None


def _service(repository: FakeMessageRepository) -> WhatsAppStatusUpdateService:
    return WhatsAppStatusUpdateService(message_repository=repository, supabase_factory=None)


def _status_event(status: str) -> MetaWhatsAppStatusEvent:
    return MetaWhatsAppStatusEvent(
        external_message_id="wamid.outbound-1",
        status=status,
        event_at=EVENT_AT,
        recipient_id="919876543210",
        metadata={
            "provider": "whatsapp",
            "source": "meta",
            "status": status,
            "recipient_id": "919876543210",
        },
    )


def _message(
    *,
    organization_id: UUID = ORG_A,
    status: MessageStatus,
    delivered_at: datetime | None = None,
    direction: str = "outbound",
    sender_type: str = "human",
) -> MessageRead:
    return MessageRead(
        id=uuid4(),
        organization_id=organization_id,
        conversation_id=CONVERSATION_ID,
        customer_id=CUSTOMER_ID,
        channel=ChannelType.WHATSAPP,
        direction=direction,
        sender_type=sender_type,
        external_message_id="wamid.outbound-1",
        message_type="text",
        body="Outbound message",
        status=status,
        generated_by_ai=False,
        sent_by_human=True,
        provider_payload={},
        metadata={},
        delivered_at=delivered_at,
        created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )


def _org_id(value) -> UUID:
    if isinstance(value, OrganizationContext):
        return value.organization_id
    return value

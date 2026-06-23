import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from postgrest.exceptions import APIError

from app.db.models.common import ChannelType, MessageStatus
from app.db.models.records import MessageCreate, MessageRead
from app.services.whatsapp_conversation_resolution import WhatsAppConversationResolution
from app.services.whatsapp_customer_identity_resolution import WhatsAppCustomerIdentityResolution
from app.services.whatsapp_message_persistence import WhatsAppMessagePersistenceService
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolution
from app.services.whatsapp_payloads import parse_meta_whatsapp_webhook


FIXTURES_DIR = Path(__file__).parent / "fixtures"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
CUSTOMER_ID = UUID("33333333-3333-3333-3333-333333333333")
CONVERSATION_ID = UUID("44444444-4444-4444-4444-444444444444")
MESSAGE_ID = UUID("55555555-5555-5555-5555-555555555555")


class FakeMessageRepository:
    def __init__(
        self,
        existing: list[MessageRead] | None = None,
        rejected_message_type: str | None = None,
        fail_once_external_message_ids: set[str] | None = None,
    ) -> None:
        self.messages = existing or []
        self.created_payloads: list[MessageCreate] = []
        self.rejected_message_type = rejected_message_type
        self.fail_once_external_message_ids = fail_once_external_message_ids or set()

    def get_by_external_message_id(self, organization_id, external_message_id, channel=None):
        return next(
            (
                message
                for message in self.messages
                if (
                    message.organization_id == organization_id.organization_id
                    and message.external_message_id == external_message_id
                    and (channel is None or message.channel == channel)
                )
            ),
            None,
        )

    def create(self, organization_id, payload):
        if payload.message_type == self.rejected_message_type:
            raise APIError({"code": "23514", "message": "check constraint violation"})
        if payload.external_message_id in self.fail_once_external_message_ids:
            self.fail_once_external_message_ids.remove(payload.external_message_id)
            raise APIError({"code": "XX000", "message": "transient insert failure"})
        self.created_payloads.append(payload)
        message = _message(
            id=MESSAGE_ID,
            external_message_id=payload.external_message_id,
            message_type=payload.message_type,
            body=payload.body,
            metadata=payload.metadata,
            external_created_at=payload.external_created_at,
            external_event_id=payload.external_event_id,
            webhook_delivery_id=payload.webhook_delivery_id,
        )
        self.messages.append(message)
        return message


class FakeConversationRepository:
    def __init__(self, fail_update: bool = False) -> None:
        self.fail_update = fail_update
        self.updates = []

    def update_last_message(self, organization_id, conversation_id, last_message_id, last_message_at):
        self.updates.append((organization_id, conversation_id, last_message_id, last_message_at))
        if self.fail_update:
            raise RuntimeError("update failed")
        return None


def test_persists_inbound_text_message() -> None:
    message_repository = FakeMessageRepository()
    conversation_repository = FakeConversationRepository()
    service = _service(message_repository, conversation_repository)

    results = service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is True
    assert results[0].duplicate is False
    assert len(message_repository.created_payloads) == 1
    created = message_repository.created_payloads[0]
    assert created.channel == ChannelType.WHATSAPP
    assert created.direction == "inbound"
    assert created.sender_type == "customer"
    assert created.customer_id == CUSTOMER_ID
    assert created.conversation_id == CONVERSATION_ID
    assert created.external_message_id == "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA="
    assert created.external_event_id == created.external_message_id
    assert created.webhook_delivery_id is None
    assert created.metadata["webhook_delivery_id"] == "delivery-123"
    assert created.message_type == "text"
    assert created.body == "Hi, is the blue kurti available in M?"
    assert created.external_created_at == datetime.fromtimestamp(1782144000, tz=timezone.utc)


def test_duplicate_inbound_message_returns_existing_without_insert() -> None:
    existing = _message(external_message_id="wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA=")
    message_repository = FakeMessageRepository(existing=[existing])
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is True
    assert results[0].duplicate is True
    assert results[0].message_id == existing.id
    assert message_repository.created_payloads == []


def test_multi_message_webhook_delivery_persists_each_message_without_delivery_unique_key() -> None:
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload_with_text_messages("wamid.first", "wamid.second"),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert [result.persisted for result in results] == [True, True]
    assert [payload.external_message_id for payload in message_repository.created_payloads] == [
        "wamid.first",
        "wamid.second",
    ]
    assert [payload.webhook_delivery_id for payload in message_repository.created_payloads] == [None, None]
    assert [
        payload.metadata["webhook_delivery_id"]
        for payload in message_repository.created_payloads
    ] == ["delivery-123", "delivery-123"]


def test_partial_failure_then_retry_persists_missing_message_by_external_message_id() -> None:
    message_repository = FakeMessageRepository(fail_once_external_message_ids={"wamid.second"})
    service = _service(message_repository, FakeConversationRepository())
    payload = _payload_with_text_messages("wamid.first", "wamid.second")

    try:
        service.persist_inbound(
            payload=payload,
            organization_resolution=_organization_resolution(),
            customer_identity_resolution=_customer_identity_resolution(),
            conversation_resolution=_conversation_resolution(),
            webhook_delivery_id="delivery-123",
        )
    except APIError:
        pass

    assert [message.external_message_id for message in message_repository.messages] == ["wamid.first"]

    retry_results = service.persist_inbound(
        payload=payload,
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert [result.persisted for result in retry_results] == [True, True]
    assert [result.duplicate for result in retry_results] == [True, False]
    assert [message.external_message_id for message in message_repository.messages] == [
        "wamid.first",
        "wamid.second",
    ]


def test_duplicate_webhook_delivery_with_already_persisted_messages_creates_no_messages() -> None:
    message_repository = FakeMessageRepository(
        existing=[
            _message(external_message_id="wamid.first"),
            _message(external_message_id="wamid.second"),
        ]
    )
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload_with_text_messages("wamid.first", "wamid.second"),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert [result.duplicate for result in results] == [True, True]
    assert message_repository.created_payloads == []


def test_duplicate_webhook_delivery_with_partially_persisted_messages_creates_only_missing_message() -> None:
    message_repository = FakeMessageRepository(existing=[_message(external_message_id="wamid.first")])
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload_with_text_messages("wamid.first", "wamid.second"),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert [result.duplicate for result in results] == [True, False]
    assert [payload.external_message_id for payload in message_repository.created_payloads] == [
        "wamid.second"
    ]


def test_missing_conversation_id_skips_message() -> None:
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(conversation_id=None),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is False
    assert results[0].skipped_reason == "missing_conversation_id"
    assert message_repository.created_payloads == []


def test_missing_customer_id_skips_message() -> None:
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(customer_id=None),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is False
    assert results[0].skipped_reason == "missing_customer_id"
    assert message_repository.created_payloads == []


def test_missing_external_message_id_skips_message() -> None:
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload_without_message_id(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is False
    assert results[0].skipped_reason == "missing_external_message_id"
    assert message_repository.created_payloads == []


def test_persists_metadata_only_image() -> None:
    created = _persist_media_message(_payload("meta_whatsapp_unsupported_media.json"))

    assert created.message_type == "image"
    assert created.body is None
    assert created.metadata["media"] == {
        "id": "MEDIA_123",
        "mime_type": "image/jpeg",
        "sha256": "mocked-sha256",
    }


def test_persists_metadata_only_document() -> None:
    created = _persist_media_message(
        _payload_with_message(
            "document",
            {
                "id": "DOCUMENT_123",
                "mime_type": "application/pdf",
                "sha256": "document-sha256",
                "filename": "invoice.pdf",
            },
        )
    )

    assert created.message_type == "document"
    assert created.body is None
    assert created.metadata["media"]["filename"] == "invoice.pdf"
    assert "url" not in created.metadata["media"]


def test_persists_metadata_only_audio() -> None:
    created = _persist_media_message(
        _payload_with_message(
            "audio",
            {
                "id": "AUDIO_123",
                "mime_type": "audio/ogg",
                "sha256": "audio-sha256",
                "voice": True,
            },
        )
    )

    assert created.message_type == "audio"
    assert created.body is None
    assert created.metadata["media"]["voice"] is True


def test_unsupported_message_type_persists_metadata_only() -> None:
    created = _persist_media_message(_payload_with_message("sticker", {"id": "STICKER_123"}))

    assert created.message_type == "sticker"
    assert created.body is None
    assert created.metadata["unsupported_message_type"] == "sticker"


def test_unsupported_message_type_skips_when_schema_rejects_it() -> None:
    message_repository = FakeMessageRepository(rejected_message_type="sticker")
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload_with_message("sticker", {"id": "STICKER_123"}),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is False
    assert results[0].skipped_reason == "unsupported_message_type_not_persisted"
    assert message_repository.created_payloads == []


def test_status_only_event_creates_no_message() -> None:
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())

    results = service.persist_inbound(
        payload=_payload("meta_whatsapp_status_event.json"),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is False
    assert results[0].skipped_reason == "missing_inbound_message"
    assert message_repository.created_payloads == []


def test_conversation_last_message_fields_update_after_insert() -> None:
    conversation_repository = FakeConversationRepository()
    service = _service(FakeMessageRepository(), conversation_repository)

    service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert len(conversation_repository.updates) == 1
    _, conversation_id, last_message_id, last_message_at = conversation_repository.updates[0]
    assert conversation_id == CONVERSATION_ID
    assert last_message_id == MESSAGE_ID
    assert last_message_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_conversation_update_failure_still_returns_persisted() -> None:
    service = _service(FakeMessageRepository(), FakeConversationRepository(fail_update=True))

    results = service.persist_inbound(
        payload=_payload(),
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )

    assert results[0].persisted is True


def _persist_media_message(payload):
    message_repository = FakeMessageRepository()
    service = _service(message_repository, FakeConversationRepository())
    service.persist_inbound(
        payload=payload,
        organization_resolution=_organization_resolution(),
        customer_identity_resolution=_customer_identity_resolution(),
        conversation_resolution=_conversation_resolution(),
        webhook_delivery_id="delivery-123",
    )
    return message_repository.created_payloads[0]


def _service(message_repository, conversation_repository):
    return WhatsAppMessagePersistenceService(
        message_repository=message_repository,
        conversation_repository=conversation_repository,
    )


def _payload(fixture_name: str = "meta_whatsapp_text_message.json"):
    return parse_meta_whatsapp_webhook((FIXTURES_DIR / fixture_name).read_bytes())


def _payload_without_message_id():
    payload = json.loads((FIXTURES_DIR / "meta_whatsapp_text_message.json").read_text())
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    return parse_meta_whatsapp_webhook(json.dumps(payload).encode())


def _payload_with_message(message_type: str, content: dict):
    payload = json.loads((FIXTURES_DIR / "meta_whatsapp_text_message.json").read_text())
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message["id"] = f"wamid.{message_type}"
    message["type"] = message_type
    message.pop("text", None)
    message[message_type] = content
    return parse_meta_whatsapp_webhook(json.dumps(payload).encode())


def _payload_with_text_messages(*message_ids: str):
    payload = json.loads((FIXTURES_DIR / "meta_whatsapp_text_message.json").read_text())
    template = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {
            **template,
            "id": message_id,
            "text": {"body": f"Body for {message_id}"},
        }
        for message_id in message_ids
    ]
    return parse_meta_whatsapp_webhook(json.dumps(payload).encode())


def _organization_resolution() -> WhatsAppOrganizationResolution:
    return WhatsAppOrganizationResolution(
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        phone_number_id="PHONE_NUMBER_123",
        whatsapp_business_account_id="WABA_123",
        provider_metadata={},
    )


def _customer_identity_resolution(customer_id: UUID | None = CUSTOMER_ID):
    return WhatsAppCustomerIdentityResolution(
        organization_id=ORGANIZATION_ID,
        provider="whatsapp",
        wa_id="919876543210",
        identity_id=None,
        customer_id=customer_id,
        customer_creation_required=customer_id is None,
    )


def _conversation_resolution(conversation_id: UUID | None = CONVERSATION_ID):
    return WhatsAppConversationResolution(
        organization_id=ORGANIZATION_ID,
        customer_id=CUSTOMER_ID,
        channel="whatsapp",
        conversation_id=conversation_id,
        existing_conversation=conversation_id is not None,
        conversation_creation_required=conversation_id is None,
        conversation_resolution_conflict=False,
    )


def _message(
    id: UUID = MESSAGE_ID,
    external_message_id: str | None = None,
    message_type: str = "text",
    body: str | None = "body",
    metadata: dict | None = None,
    external_created_at: datetime | None = None,
    external_event_id: str | None = None,
    webhook_delivery_id: str | None = None,
) -> MessageRead:
    return MessageRead(
        id=id,
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        customer_id=CUSTOMER_ID,
        channel=ChannelType.WHATSAPP,
        direction="inbound",
        sender_type="customer",
        external_message_id=external_message_id,
        external_event_id=external_event_id,
        webhook_delivery_id=webhook_delivery_id,
        message_type=message_type,
        body=body,
        status=MessageStatus.RECEIVED,
        metadata=metadata or {},
        external_created_at=external_created_at,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

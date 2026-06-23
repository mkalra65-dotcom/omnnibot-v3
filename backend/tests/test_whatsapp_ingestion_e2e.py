import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes.whatsapp_webhooks import (
    get_whatsapp_conversation_resolution_service,
    get_whatsapp_customer_identity_resolution_service,
    get_whatsapp_message_persistence_service,
    get_whatsapp_organization_resolution_service,
    get_whatsapp_status_update_service,
    get_webhook_event_repository,
)
from app.core.config import settings
from app.db.models.common import (
    ChannelType,
    ConversationStatus,
    CustomerStatus,
    LeadStage,
    MessageStatus,
    PaginationOptions,
    RepositoryPage,
    WhatsAppAccountStatus,
)
from app.db.models.queries import ConversationFilters
from app.db.models.records import (
    ConversationCreate,
    ConversationRead,
    CustomerCreate,
    CustomerIdentityCreate,
    CustomerIdentityRead,
    CustomerRead,
    MessageRead,
    WebhookEventCreate,
    WhatsAppAccountRead,
)
from app.main import app
from app.services.whatsapp_conversation_resolution import WhatsAppConversationResolutionService
from app.services.whatsapp_customer_identity_resolution import WhatsAppCustomerIdentityResolutionService
from app.services.whatsapp_message_persistence import WhatsAppMessagePersistenceService
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolutionService
from app.services.whatsapp_status_updates import WhatsAppStatusUpdateService
from app.services.whatsapp_signature import build_meta_signature


APP_SECRET = "test-app-secret"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
ACCOUNT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ACCOUNT_ID = UUID("44444444-4444-4444-4444-444444444444")
CUSTOMER_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_CUSTOMER_ID = UUID("66666666-6666-6666-6666-666666666666")
IDENTITY_ID = UUID("77777777-7777-7777-7777-777777777777")
CONVERSATION_ID = UUID("88888888-8888-8888-8888-888888888888")
WA_ID = "919876543210"
PHONE_NUMBER_ID = "PHONE_NUMBER_123"
WABA_ID = "WABA_123"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    state = InMemoryWhatsAppState()
    state.whatsapp_accounts.append(_account())
    state.customers.append(_customer())
    state.customer_identities.append(_identity())
    state.conversations.append(_conversation())

    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: WhatsAppOrganizationResolutionService(repository=state.whatsapp_accounts_repository)
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: WhatsAppCustomerIdentityResolutionService(repository=state.customer_repository)
    )
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: WhatsAppConversationResolutionService(repository=state.conversation_repository)
    )
    app.dependency_overrides[get_whatsapp_message_persistence_service] = (
        lambda: WhatsAppMessagePersistenceService(
            message_repository=state.message_repository,
            conversation_repository=state.conversation_repository,
        )
    )
    app.dependency_overrides[get_whatsapp_status_update_service] = (
        lambda: WhatsAppStatusUpdateService(
            message_repository=state.message_repository,
            supabase_factory=None,
        )
    )
    app.dependency_overrides[get_webhook_event_repository] = lambda: state.webhook_event_repository

    return state


def test_text_message_e2e_creates_exactly_one_crm_message(harness) -> None:
    response = _post_signed(_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(harness.webhook_events) == 1
    assert [message.body for message in harness.messages] == ["Hi, is the blue kurti available in M?"]
    message = harness.messages[0]
    assert message.organization_id == ORGANIZATION_ID
    assert message.customer_id == CUSTOMER_ID
    assert message.conversation_id == CONVERSATION_ID
    assert message.channel == ChannelType.WHATSAPP
    assert message.direction == "inbound"
    assert message.sender_type == "customer"
    assert message.external_message_id == "wamid.text-1"
    assert message.webhook_delivery_id is None
    assert message.metadata["webhook_delivery_id"] == harness.webhook_events[0].delivery_id


def test_multi_message_delivery_creates_multiple_crm_messages(harness) -> None:
    response = _post_signed(_payload(messages=[_message("wamid.first"), _message("wamid.second")]))

    assert response.status_code == 200
    assert len(harness.webhook_events) == 1
    assert [message.external_message_id for message in harness.messages] == [
        "wamid.first",
        "wamid.second",
    ]
    assert [message.webhook_delivery_id for message in harness.messages] == [None, None]
    assert {
        message.metadata["webhook_delivery_id"] for message in harness.messages
    } == {harness.webhook_events[0].delivery_id}


def test_duplicate_delivery_creates_no_duplicate_crm_messages(harness) -> None:
    raw_body = _payload(messages=[_message("wamid.first"), _message("wamid.second")])

    first_response = _post_signed(raw_body)
    second_response = _post_signed(raw_body)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == {"status": "accepted"}
    assert len(harness.webhook_events) == 1
    assert [message.external_message_id for message in harness.messages] == [
        "wamid.first",
        "wamid.second",
    ]
    assert len(harness.message_repository.created_payloads) == 2


def test_retry_after_partial_failure_recovers_missing_messages(harness) -> None:
    harness.message_repository.fail_after_create_count = 1
    raw_body = _payload(messages=[_message("wamid.first"), _message("wamid.second")])
    client = TestClient(app, raise_server_exceptions=False)

    first_response = _post_signed(raw_body, client=client)
    harness.message_repository.fail_after_create_count = None
    retry_response = _post_signed(raw_body)

    assert first_response.status_code == 500
    assert retry_response.status_code == 200
    assert retry_response.json() == {"status": "accepted"}
    assert len(harness.webhook_events) == 1
    assert [message.external_message_id for message in harness.messages] == [
        "wamid.first",
        "wamid.second",
    ]
    assert len(harness.message_repository.created_payloads) == 2


def test_cross_organization_safety_does_not_resolve_same_wa_id_in_other_org(harness) -> None:
    harness.customer_identities[:] = [
        _identity(
            id=uuid4(),
            organization_id=OTHER_ORGANIZATION_ID,
            customer_id=OTHER_CUSTOMER_ID,
        )
    ]
    harness.customers[:] = [_customer(id=OTHER_CUSTOMER_ID, organization_id=OTHER_ORGANIZATION_ID)]

    response = _post_signed(_payload())

    assert response.status_code == 200
    assert len(harness.webhook_events) == 1
    assert harness.webhook_events[0].organization_id == ORGANIZATION_ID
    assert len(harness.customers) == 2
    assert len(harness.customer_identities) == 2
    assert len(harness.conversations) == 2
    assert len(harness.messages) == 1
    assert harness.messages[0].organization_id == ORGANIZATION_ID
    assert harness.messages[0].customer_id != OTHER_CUSTOMER_ID
    assert harness.customer_repository.identity_lookup_organization_ids == [ORGANIZATION_ID]


def test_first_time_inbound_text_creates_customer_identity_conversation_message(harness) -> None:
    harness.customers.clear()
    harness.customer_identities.clear()
    harness.conversations.clear()

    response = _post_signed(_payload())

    assert response.status_code == 200
    assert len(harness.customers) == 1
    assert len(harness.customer_identities) == 1
    assert len(harness.conversations) == 1
    assert len(harness.messages) == 1
    customer = harness.customers[0]
    identity = harness.customer_identities[0]
    conversation = harness.conversations[0]
    message = harness.messages[0]
    assert customer.organization_id == ORGANIZATION_ID
    assert customer.display_name == "Asha Buyer"
    assert customer.phone_number == WA_ID
    assert customer.metadata["wa_id"] == WA_ID
    assert identity.organization_id == ORGANIZATION_ID
    assert identity.customer_id == customer.id
    assert identity.provider == "whatsapp"
    assert identity.provider_user_id == WA_ID
    assert identity.provider_phone is None
    assert identity.metadata["wa_id"] == WA_ID
    assert conversation.organization_id == ORGANIZATION_ID
    assert conversation.customer_id == customer.id
    assert conversation.channel == ChannelType.WHATSAPP
    assert conversation.status == ConversationStatus.OPEN
    assert message.customer_id == customer.id
    assert message.conversation_id == conversation.id
    assert message.external_message_id == "wamid.text-1"


def test_first_time_inbound_media_creates_customer_identity_conversation_message(harness) -> None:
    harness.customers.clear()
    harness.customer_identities.clear()
    harness.conversations.clear()

    response = _post_signed(
        _payload(messages=[_message("wamid.image-first", "image", {"id": "MEDIA_123", "mime_type": "image/jpeg"})])
    )

    assert response.status_code == 200
    assert len(harness.customers) == 1
    assert len(harness.customer_identities) == 1
    assert len(harness.conversations) == 1
    assert len(harness.messages) == 1
    assert harness.messages[0].message_type == "image"
    assert harness.messages[0].metadata["media"]["id"] == "MEDIA_123"


def test_no_open_conversation_creates_conversation(harness) -> None:
    harness.conversations.clear()

    response = _post_signed(_payload())

    assert response.status_code == 200
    assert len(harness.conversations) == 1
    assert harness.conversations[0].customer_id == CUSTOMER_ID
    assert harness.conversations[0].status == ConversationStatus.OPEN
    assert harness.messages[0].conversation_id == harness.conversations[0].id


def test_existing_open_conversation_reused(harness) -> None:
    response = _post_signed(_payload())

    assert response.status_code == 200
    assert len(harness.conversations) == 1
    assert harness.messages[0].conversation_id == CONVERSATION_ID


def test_duplicate_open_conversations_fail_safely_without_message(harness) -> None:
    harness.conversations.append(_conversation(id=uuid4()))
    client = TestClient(app, raise_server_exceptions=False)

    response = _post_signed(_payload(), client=client)

    assert response.status_code == 409
    assert response.json() == {"detail": "WhatsApp conversation resolution conflict"}
    assert harness.messages == []


def test_duplicate_inbound_message_does_not_create_duplicate_customer_conversation_or_message(harness) -> None:
    harness.customers.clear()
    harness.customer_identities.clear()
    harness.conversations.clear()
    raw_body = _payload()

    first_response = _post_signed(raw_body)
    second_response = _post_signed(raw_body)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert len(harness.customers) == 1
    assert len(harness.customer_identities) == 1
    assert len(harness.conversations) == 1
    assert len(harness.messages) == 1


def test_missing_wa_id_inbound_message_rejected_without_message_loss(harness) -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = _post_signed(_payload(contacts=[]), client=client)

    assert response.status_code == 400
    assert response.json() == {"detail": "Malformed WhatsApp customer identity"}
    assert harness.messages == []


def test_status_only_event_creates_webhook_event_and_no_crm_message(harness) -> None:
    response = _post_signed(_payload(messages=[], statuses=[_status("wamid.status-1")], contacts=[]))

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(harness.webhook_events) == 1
    assert harness.webhook_events[0].event_type == "status"
    assert harness.messages == []


def test_status_only_event_updates_matching_outbound_message(harness) -> None:
    harness.messages.append(
        _outbound_message(
            external_message_id="wamid.outbound-1",
            status=MessageStatus.SENT,
        )
    )

    response = _post_signed(
        _payload(messages=[], statuses=[_status("wamid.outbound-1")], contacts=[])
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(harness.messages) == 1
    message = harness.messages[0]
    assert message.status == MessageStatus.DELIVERED
    assert message.delivered_at == datetime.fromtimestamp(1782144060, tz=timezone.utc)
    assert message.provider_payload["last_status_event"]["status"] == "delivered"


@pytest.mark.parametrize(
    ("message_type", "content"),
    [
        ("image", {"id": "MEDIA_123", "mime_type": "image/jpeg", "sha256": "image-sha256"}),
        (
            "document",
            {
                "id": "DOCUMENT_123",
                "mime_type": "application/pdf",
                "sha256": "document-sha256",
                "filename": "invoice.pdf",
            },
        ),
        ("audio", {"id": "AUDIO_123", "mime_type": "audio/ogg", "sha256": "audio-sha256", "voice": True}),
    ],
)
def test_media_metadata_messages_create_metadata_only_crm_messages(
    harness,
    message_type: str,
    content: dict,
) -> None:
    response = _post_signed(_payload(messages=[_message(f"wamid.{message_type}", message_type, content)]))

    assert response.status_code == 200
    assert len(harness.messages) == 1
    message = harness.messages[0]
    assert message.message_type == message_type
    assert message.body is None
    assert message.media_url is None
    assert message.provider_payload == {}
    assert message.metadata["media"]["id"] == content["id"]
    assert "url" not in message.metadata["media"]


def test_unsupported_message_type_returns_accepted_without_crashing(harness) -> None:
    response = _post_signed(_payload(messages=[_message("wamid.sticker", "sticker", {"id": "STICKER_123"})]))

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(harness.messages) == 1
    assert harness.messages[0].message_type == "sticker"
    assert harness.messages[0].metadata["unsupported_message_type"] == "sticker"


def test_invalid_signature_creates_no_writes(harness) -> None:
    response = TestClient(app).post(
        "/api/v1/webhooks/whatsapp",
        content=_payload(),
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )

    assert response.status_code == 403
    assert harness.webhook_events == []
    assert harness.messages == []


def test_malformed_payload_creates_no_writes(harness) -> None:
    raw_body = b'{"object": "whatsapp_business_account"'
    response = _post_signed(raw_body)

    assert response.status_code == 400
    assert harness.webhook_events == []
    assert harness.messages == []


def test_unresolved_organization_creates_no_crm_writes(harness) -> None:
    harness.whatsapp_accounts.clear()

    response = _post_signed(_payload())

    assert response.status_code == 403
    assert harness.webhook_events == []
    assert harness.messages == []


class InMemoryWhatsAppState:
    def __init__(self) -> None:
        self.whatsapp_accounts: list[WhatsAppAccountRead] = []
        self.customer_identities: list[CustomerIdentityRead] = []
        self.customers: list[CustomerRead] = []
        self.conversations: list[ConversationRead] = []
        self.messages: list[MessageRead] = []
        self.webhook_events: list[WebhookEventCreate] = []
        self.whatsapp_accounts_repository = InMemoryWhatsAppAccountRepository(self)
        self.customer_repository = InMemoryCustomerRepository(self)
        self.conversation_repository = InMemoryConversationRepository(self)
        self.message_repository = InMemoryMessageRepository(self)
        self.webhook_event_repository = InMemoryWebhookEventRepository(self)


class InMemoryWhatsAppAccountRepository:
    def __init__(self, state: InMemoryWhatsAppState) -> None:
        self.state = state

    def list_active_by_phone_number_id(self, phone_number_id: str, limit: int = 2):
        matches = [
            account
            for account in self.state.whatsapp_accounts
            if account.phone_number_id == phone_number_id
            and account.status == WhatsAppAccountStatus.ACTIVE
        ]
        return matches[:limit]


class InMemoryCustomerRepository:
    def __init__(self, state: InMemoryWhatsAppState) -> None:
        self.state = state
        self.identity_lookup_organization_ids: list[UUID] = []

    def list_identities_by_provider_user_id(
        self,
        organization_id: UUID,
        provider: str,
        provider_user_id: str,
        limit: int = 2,
    ):
        self.identity_lookup_organization_ids.append(organization_id)
        matches = [
            identity
            for identity in self.state.customer_identities
            if identity.organization_id == organization_id
            and identity.provider == provider
            and identity.provider_user_id == provider_user_id
        ]
        return matches[:limit]

    def get_by_id(self, organization_id: UUID, customer_id: UUID):
        return next(
            (
                customer
                for customer in self.state.customers
                if customer.organization_id == organization_id and customer.id == customer_id
            ),
            None,
        )

    def create(self, organization_id, payload: CustomerCreate):
        organization_uuid = _organization_id(organization_id)
        customer = CustomerRead(
            id=uuid4(),
            organization_id=organization_uuid,
            display_name=payload.display_name,
            email=payload.email,
            phone_number=payload.phone_number,
            status=payload.status,
            lead_score=payload.lead_score,
            lead_stage=payload.lead_stage,
            purchase_stage=payload.purchase_stage,
            lifetime_value_amount=payload.lifetime_value_amount,
            lifetime_value_currency=payload.lifetime_value_currency,
            order_count=payload.order_count,
            first_seen_at=payload.first_seen_at,
            last_seen_at=payload.last_seen_at,
            tags=payload.tags,
            profile=payload.profile,
            metadata=payload.metadata,
        )
        self.state.customers.append(customer)
        return customer

    def create_identity(self, organization_id, payload: CustomerIdentityCreate):
        organization_uuid = _organization_id(organization_id)
        identity = CustomerIdentityRead(
            id=uuid4(),
            organization_id=organization_uuid,
            customer_id=payload.customer_id,
            provider=payload.provider,
            provider_user_id=payload.provider_user_id,
            provider_username=payload.provider_username,
            provider_phone=payload.provider_phone,
            metadata=payload.metadata,
        )
        self.state.customer_identities.append(identity)
        return identity


class InMemoryConversationRepository:
    def __init__(self, state: InMemoryWhatsAppState) -> None:
        self.state = state
        self.last_message_updates: list[tuple[UUID, UUID, datetime | None]] = []

    def list_by_customer(
        self,
        organization_id: UUID,
        customer_id: UUID,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort=None,
    ):
        matches = [
            conversation
            for conversation in self.state.conversations
            if conversation.organization_id == organization_id
            and conversation.customer_id == customer_id
            and (filters is None or filters.status is None or conversation.status == filters.status)
            and (filters is None or filters.channel is None or conversation.channel == filters.channel)
        ]
        if pagination and pagination.limit is not None:
            matches = matches[: pagination.limit]
        return RepositoryPage(
            items=matches,
            total=len(matches),
            page=1,
            page_size=len(matches),
            offset=0,
            limit=pagination.limit if pagination and pagination.limit else len(matches),
        )

    def update_last_message(self, organization_id, conversation_id, last_message_id, last_message_at):
        organization_uuid = _organization_id(organization_id)
        self.last_message_updates.append((organization_uuid, last_message_id, last_message_at))
        for index, conversation in enumerate(self.state.conversations):
            if (
                conversation.organization_id == organization_uuid
                and conversation.id == conversation_id
            ):
                self.state.conversations[index] = conversation.model_copy(
                    update={
                        "last_message_id": last_message_id,
                        "last_message_at": last_message_at,
                    }
                )

    def create(self, organization_id, payload: ConversationCreate):
        organization_uuid = _organization_id(organization_id)
        conversation = ConversationRead(
            id=uuid4(),
            organization_id=organization_uuid,
            customer_id=payload.customer_id,
            channel=payload.channel,
            external_conversation_id=payload.external_conversation_id,
            status=payload.status,
            handoff_status=payload.handoff_status,
            priority=payload.priority,
            assigned_membership_id=payload.assigned_membership_id,
            state=payload.state,
            summary=payload.summary,
            metadata=payload.metadata,
        )
        self.state.conversations.append(conversation)
        return conversation


class InMemoryMessageRepository:
    def __init__(self, state: InMemoryWhatsAppState) -> None:
        self.state = state
        self.created_payloads = []
        self.fail_after_create_count: int | None = None

    def get_by_external_message_id(
        self,
        organization_id,
        external_message_id,
        channel=None,
        direction=None,
    ):
        return next(
            (
                message
                for message in self.state.messages
                if message.organization_id == organization_id.organization_id
                and message.external_message_id == external_message_id
                and (channel is None or message.channel == channel)
                and (direction is None or message.direction == direction)
            ),
            None,
        )

    def create(self, organization_id, payload):
        message = MessageRead(
            id=uuid4(),
            organization_id=organization_id.organization_id,
            conversation_id=payload.conversation_id,
            customer_id=payload.customer_id,
            channel=payload.channel,
            direction=payload.direction,
            sender_type=payload.sender_type,
            sender_user_id=payload.sender_user_id,
            external_message_id=payload.external_message_id,
            external_event_id=payload.external_event_id,
            webhook_delivery_id=payload.webhook_delivery_id,
            message_type=payload.message_type,
            body=payload.body,
            media_url=payload.media_url,
            status=MessageStatus.RECEIVED,
            generated_by_ai=payload.generated_by_ai,
            sent_by_human=payload.sent_by_human,
            provider_payload=payload.provider_payload,
            metadata=payload.metadata,
            external_created_at=payload.external_created_at,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.state.messages.append(message)
        self.created_payloads.append(payload)
        if (
            self.fail_after_create_count is not None
            and len(self.created_payloads) >= self.fail_after_create_count
        ):
            self.fail_after_create_count = None
            raise RuntimeError("simulated failure after partial message persistence")
        return message

    def update(self, organization_id, record_id, payload):
        for index, message in enumerate(self.state.messages):
            if (
                message.organization_id == organization_id.organization_id
                and message.id == record_id
            ):
                self.state.messages[index] = message.model_copy(update=payload)
                return self.state.messages[index]
        return None


class InMemoryWebhookEventRepository:
    def __init__(self, state: InMemoryWhatsAppState) -> None:
        self.state = state

    def get_by_delivery_id(self, provider: str, delivery_id: str):
        return next(
            (
                event
                for event in self.state.webhook_events
                if event.provider == provider and event.delivery_id == delivery_id
            ),
            None,
        )

    def get_by_external_event_id(self, provider: str, external_event_id: str):
        return next(
            (
                event
                for event in self.state.webhook_events
                if event.provider == provider and event.external_event_id == external_event_id
            ),
            None,
        )

    def create(self, payload: WebhookEventCreate):
        self.state.webhook_events.append(payload)
        return payload


def _post_signed(raw_body: bytes, client: TestClient | None = None):
    client = client or TestClient(app)
    return client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": build_meta_signature(raw_body, APP_SECRET),
        },
    )


def _payload(
    *,
    messages: list[dict] | None = None,
    statuses: list[dict] | None = None,
    contacts: list[dict] | None = None,
) -> bytes:
    value = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "15551234567",
            "phone_number_id": PHONE_NUMBER_ID,
        },
    }
    if messages is None:
        messages = [_message("wamid.text-1")]
    if messages:
        value["messages"] = messages
    if statuses:
        value["statuses"] = statuses
    if contacts is None:
        contacts = [{"profile": {"name": "Asha Buyer"}, "wa_id": WA_ID}]
    if contacts:
        value["contacts"] = contacts

    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": WABA_ID,
                    "changes": [{"field": "messages", "value": value}],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _message(
    message_id: str,
    message_type: str = "text",
    content: dict | None = None,
) -> dict:
    message = {
        "from": WA_ID,
        "id": message_id,
        "timestamp": "1782144000",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = content or {"body": "Hi, is the blue kurti available in M?"}
    else:
        message[message_type] = deepcopy(content or {"id": f"{message_type.upper()}_123"})
    return message


def _status(message_id: str) -> dict:
    return {
        "id": message_id,
        "status": "delivered",
        "timestamp": "1782144060",
        "recipient_id": WA_ID,
    }


def _account(
    id: UUID = ACCOUNT_ID,
    organization_id: UUID = ORGANIZATION_ID,
    phone_number_id: str = PHONE_NUMBER_ID,
) -> WhatsAppAccountRead:
    return WhatsAppAccountRead(
        id=id,
        organization_id=organization_id,
        phone_number_id=phone_number_id,
        whatsapp_business_account_id=WABA_ID,
        display_phone_number="15551234567",
        status=WhatsAppAccountStatus.ACTIVE,
        metadata={},
    )


def _identity(
    id: UUID = IDENTITY_ID,
    organization_id: UUID = ORGANIZATION_ID,
    customer_id: UUID = CUSTOMER_ID,
) -> CustomerIdentityRead:
    return CustomerIdentityRead(
        id=id,
        organization_id=organization_id,
        customer_id=customer_id,
        provider="whatsapp",
        provider_user_id=WA_ID,
        provider_username="Asha Buyer",
        provider_phone=None,
        metadata={},
    )


def _customer(
    id: UUID = CUSTOMER_ID,
    organization_id: UUID = ORGANIZATION_ID,
) -> CustomerRead:
    return CustomerRead(
        id=id,
        organization_id=organization_id,
        display_name="Asha Buyer",
        email=None,
        phone_number=None,
        status=CustomerStatus.LEAD,
        lead_stage=LeadStage.NEW,
        purchase_stage="unknown",
    )


def _conversation(
    id: UUID = CONVERSATION_ID,
    organization_id: UUID = ORGANIZATION_ID,
    customer_id: UUID = CUSTOMER_ID,
) -> ConversationRead:
    return ConversationRead(
        id=id,
        organization_id=organization_id,
        customer_id=customer_id,
        channel=ChannelType.WHATSAPP,
        status=ConversationStatus.OPEN,
        handoff_status="ai",
        priority="normal",
    )


def _outbound_message(
    *,
    external_message_id: str,
    status: MessageStatus,
    organization_id: UUID = ORGANIZATION_ID,
) -> MessageRead:
    return MessageRead(
        id=uuid4(),
        organization_id=organization_id,
        conversation_id=CONVERSATION_ID,
        customer_id=CUSTOMER_ID,
        channel=ChannelType.WHATSAPP,
        direction="outbound",
        sender_type="human",
        external_message_id=external_message_id,
        message_type="text",
        body="Outbound reply",
        status=status,
        generated_by_ai=False,
        sent_by_human=True,
        provider_payload={},
        metadata={},
        sent_at=datetime.fromtimestamp(1782144000, tz=timezone.utc)
        if status == MessageStatus.SENT
        else None,
    )


def _organization_id(value) -> UUID:
    return value.organization_id if hasattr(value, "organization_id") else value

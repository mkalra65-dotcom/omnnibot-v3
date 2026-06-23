from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

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
from app.db.models.records import WebhookEventCreate
from app.main import app
from app.services.whatsapp_customer_identity_resolution import (
    WhatsAppCustomerIdentityInputError,
    WhatsAppCustomerIdentityResolution,
)
from app.services.whatsapp_conversation_resolution import WhatsAppConversationResolution
from app.services.whatsapp_organization_resolution import (
    WhatsAppOrganizationResolution,
    WhatsAppOrganizationResolutionError,
)
from app.services.whatsapp_signature import build_meta_signature


client = TestClient(app)
FIXTURES_DIR = Path(__file__).parent / "fixtures"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
IDENTITY_ID = UUID("33333333-3333-3333-3333-333333333333")
CUSTOMER_ID = UUID("44444444-4444-4444-4444-444444444444")
CONVERSATION_ID = UUID("55555555-5555-5555-5555-555555555555")


class RecordingWebhookEventRepository:
    def __init__(self) -> None:
        self.records: list[WebhookEventCreate] = []

    def get_by_delivery_id(self, provider: str, delivery_id: str):
        return next(
            (
                record
                for record in self.records
                if record.provider == provider and record.delivery_id == delivery_id
            ),
            None,
        )

    def get_by_external_event_id(self, provider: str, external_event_id: str):
        return next(
            (
                record
                for record in self.records
                if record.provider == provider and record.external_event_id == external_event_id
            ),
            None,
        )

    def create(self, payload: WebhookEventCreate):
        self.records.append(payload)
        return payload


@pytest.fixture
def webhook_event_repository() -> RecordingWebhookEventRepository:
    return RecordingWebhookEventRepository()


@pytest.fixture(autouse=True)
def override_webhook_event_repository(webhook_event_repository):
    app.dependency_overrides[get_webhook_event_repository] = lambda: webhook_event_repository
    app.dependency_overrides[get_whatsapp_status_update_service] = (
        lambda: RecordingWhatsAppStatusUpdateService()
    )
    yield
    app.dependency_overrides.clear()


class AcceptingWhatsAppOrganizationResolutionService:
    def resolve(self, payload):
        return WhatsAppOrganizationResolution(
            organization_id=ORGANIZATION_ID,
            account_id=ACCOUNT_ID,
            phone_number_id=payload.phone_number_id,
            whatsapp_business_account_id=payload.whatsapp_business_account_id,
            provider_metadata=payload.provider_metadata,
        )


class RejectingWhatsAppOrganizationResolutionService:
    def resolve(self, payload):
        raise WhatsAppOrganizationResolutionError("unresolved")


class AcceptingWhatsAppCustomerIdentityResolutionService:
    calls = 0

    def resolve(self, payload, organization_resolution):
        self.calls += 1
        return WhatsAppCustomerIdentityResolution(
            organization_id=organization_resolution.organization_id,
            provider="whatsapp",
            wa_id=payload.wa_ids[0],
            identity_id=IDENTITY_ID,
            customer_id=CUSTOMER_ID,
            customer_creation_required=False,
        )


class MissingWhatsAppCustomerIdentityResolutionService:
    calls = 0

    def resolve(self, payload, organization_resolution):
        self.calls += 1
        return WhatsAppCustomerIdentityResolution(
            organization_id=organization_resolution.organization_id,
            provider="whatsapp",
            wa_id=payload.wa_ids[0],
            identity_id=None,
            customer_id=None,
            customer_creation_required=True,
        )


class RejectingWhatsAppCustomerIdentityResolutionService:
    def resolve(self, payload, organization_resolution):
        raise WhatsAppCustomerIdentityInputError("malformed")


class RecordingWhatsAppCustomerIdentityResolutionService:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, payload, organization_resolution):
        self.calls += 1
        return None


class RecordingWhatsAppConversationResolutionService:
    def __init__(self) -> None:
        self.calls = 0
        self.customer_ids = []

    def resolve(self, customer_identity_resolution):
        self.calls += 1
        self.customer_ids.append(customer_identity_resolution.customer_id)
        return None


class ResolvingWhatsAppConversationResolutionService(RecordingWhatsAppConversationResolutionService):
    def resolve(self, customer_identity_resolution):
        super().resolve(customer_identity_resolution)
        return WhatsAppConversationResolution(
            organization_id=customer_identity_resolution.organization_id,
            customer_id=customer_identity_resolution.customer_id,
            channel="whatsapp",
            conversation_id=CONVERSATION_ID,
            existing_conversation=True,
            conversation_creation_required=False,
            conversation_resolution_conflict=False,
        )


class RecordingWhatsAppMessagePersistenceService:
    def __init__(self) -> None:
        self.calls = []

    def persist_inbound(
        self,
        *,
        payload,
        organization_resolution,
        customer_identity_resolution,
        conversation_resolution,
        webhook_delivery_id,
    ):
        self.calls.append(
            {
                "payload": payload,
                "organization_resolution": organization_resolution,
                "customer_identity_resolution": customer_identity_resolution,
                "conversation_resolution": conversation_resolution,
                "webhook_delivery_id": webhook_delivery_id,
            }
        )
        return [SimpleNamespace(persisted=True, duplicate=False, skipped_reason=None)]


class RecordingWhatsAppStatusUpdateService:
    def __init__(self) -> None:
        self.calls = []

    def process_status_events(self, *, status_events, organization_resolution):
        self.calls.append(
            {
                "status_events": status_events,
                "organization_resolution": organization_resolution,
            }
        )
        return []


class FailingOnceWhatsAppMessagePersistenceService(RecordingWhatsAppMessagePersistenceService):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next = True

    def persist_inbound(self, **kwargs):
        results = super().persist_inbound(**kwargs)
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("message persistence failed after webhook event insert")
        return results


def test_get_webhook_verification_returns_challenge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-token")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-123"
    assert response.headers["content-type"].startswith("text/plain")


def test_get_webhook_verification_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-token")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403


def test_get_webhook_verification_rejects_unconfigured_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_token", "")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403


def test_post_webhook_accepts_valid_raw_body_signature(monkeypatch, webhook_event_repository) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    identity_resolution_service = AcceptingWhatsAppCustomerIdentityResolutionService()
    conversation_resolution_service = ResolvingWhatsAppConversationResolutionService()
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
    )
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: conversation_resolution_service
    )
    app.dependency_overrides[get_whatsapp_message_persistence_service] = (
        lambda: RecordingWhatsAppMessagePersistenceService()
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert identity_resolution_service.calls == 1
    assert conversation_resolution_service.calls == 1
    assert conversation_resolution_service.customer_ids == [CUSTOMER_ID]
    assert len(webhook_event_repository.records) == 1
    event = webhook_event_repository.records[0]
    assert event.provider == "whatsapp"
    assert event.event_type == "message"
    assert event.organization_id == ORGANIZATION_ID
    assert event.account_id == ACCOUNT_ID
    assert event.phone_number_id == "PHONE_NUMBER_123"
    assert event.signature_valid is True
    assert event.resolved is True
    assert event.external_event_id == "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA="
    assert event.delivery_id is not None
    assert event.payload_hash is not None
    assert event.payload is None
    assert event.received_at is not None


def test_post_webhook_persists_message_after_conversation_resolution(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    identity_resolution_service = AcceptingWhatsAppCustomerIdentityResolutionService()
    conversation_resolution_service = ResolvingWhatsAppConversationResolutionService()
    message_persistence_service = RecordingWhatsAppMessagePersistenceService()
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
    )
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: conversation_resolution_service
    )
    app.dependency_overrides[get_whatsapp_message_persistence_service] = (
        lambda: message_persistence_service
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert identity_resolution_service.calls == 1
    assert conversation_resolution_service.calls == 1
    assert len(message_persistence_service.calls) == 1
    persistence_call = message_persistence_service.calls[0]
    assert persistence_call["conversation_resolution"].conversation_id == CONVERSATION_ID
    assert persistence_call["customer_identity_resolution"].customer_id == CUSTOMER_ID
    assert persistence_call["webhook_delivery_id"] == webhook_event_repository.records[0].delivery_id


def test_post_webhook_rejects_malformed_payload_after_valid_signature(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    raw_body = b'{"object": "whatsapp_business_account"'
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Malformed WhatsApp webhook payload"}
    assert webhook_event_repository.records == []


def test_post_webhook_rejects_unresolved_organization_after_valid_signature(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: RejectingWhatsAppOrganizationResolutionService()
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert webhook_event_repository.records == []


def test_post_webhook_rejects_malformed_customer_identity_after_organization_resolution(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: RejectingWhatsAppCustomerIdentityResolutionService()
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Malformed WhatsApp customer identity"}


def test_post_webhook_accepts_status_event_without_customer_identity_resolution(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    identity_resolution_service = RecordingWhatsAppCustomerIdentityResolutionService()
    status_update_service = RecordingWhatsAppStatusUpdateService()
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
    )
    app.dependency_overrides[get_whatsapp_status_update_service] = (
        lambda: status_update_service
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_status_event.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert identity_resolution_service.calls == 0
    assert len(status_update_service.calls) == 1
    assert status_update_service.calls[0]["organization_resolution"].organization_id == ORGANIZATION_ID
    assert len(status_update_service.calls[0]["status_events"]) == 1
    assert status_update_service.calls[0]["status_events"][0].status == "delivered"
    assert len(webhook_event_repository.records) == 1
    event = webhook_event_repository.records[0]
    assert event.event_type == "status"
    assert event.organization_id == ORGANIZATION_ID
    assert event.external_event_id == "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA="
    assert event.resolved is True


def test_post_webhook_accepts_duplicate_event_without_second_webhook_event(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    identity_resolution_service = AcceptingWhatsAppCustomerIdentityResolutionService()
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
    )
    conversation_resolution_service = ResolvingWhatsAppConversationResolutionService()
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: conversation_resolution_service
    )
    message_persistence_service = RecordingWhatsAppMessagePersistenceService()
    app.dependency_overrides[get_whatsapp_message_persistence_service] = (
        lambda: message_persistence_service
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_duplicate_delivery.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        first_response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
        second_response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == {"status": "accepted"}
    assert len(webhook_event_repository.records) == 1
    assert identity_resolution_service.calls == 2
    assert conversation_resolution_service.calls == 2
    assert len(message_persistence_service.calls) == 2


def test_post_webhook_retries_message_persistence_when_duplicate_event_already_exists(
    monkeypatch, webhook_event_repository
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: AcceptingWhatsAppCustomerIdentityResolutionService()
    )
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: ResolvingWhatsAppConversationResolutionService()
    )
    message_persistence_service = FailingOnceWhatsAppMessagePersistenceService()
    app.dependency_overrides[get_whatsapp_message_persistence_service] = (
        lambda: message_persistence_service
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_duplicate_delivery.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/webhooks/whatsapp",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": signature,
                },
            )
        retry_response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert retry_response.status_code == 200
    assert retry_response.json() == {"status": "accepted"}
    assert len(webhook_event_repository.records) == 1
    assert len(message_persistence_service.calls) == 2


def test_post_webhook_rejects_customer_resolution_without_customer_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    identity_resolution_service = MissingWhatsAppCustomerIdentityResolutionService()
    conversation_resolution_service = RecordingWhatsAppConversationResolutionService()
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
    )
    app.dependency_overrides[get_whatsapp_conversation_resolution_service] = (
        lambda: conversation_resolution_service
    )
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    try:
        response = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "WhatsApp customer identity did not resolve to a customer"}
    assert identity_resolution_service.calls == 1
    assert conversation_resolution_service.calls == 0


def test_post_webhook_rejects_invalid_signature(monkeypatch, webhook_event_repository) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 403
    assert webhook_event_repository.records == []


def test_post_webhook_rejects_missing_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 403


def test_post_webhook_rejects_unconfigured_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, "test-app-secret")

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 403

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.v1.routes.whatsapp_webhooks import (
    get_whatsapp_conversation_resolution_service,
    get_whatsapp_customer_identity_resolution_service,
    get_whatsapp_organization_resolution_service,
)
from app.core.config import settings
from app.main import app
from app.services.whatsapp_customer_identity_resolution import (
    WhatsAppCustomerIdentityInputError,
    WhatsAppCustomerIdentityResolution,
)
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


def test_post_webhook_accepts_valid_raw_body_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    identity_resolution_service = AcceptingWhatsAppCustomerIdentityResolutionService()
    conversation_resolution_service = RecordingWhatsAppConversationResolutionService()
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

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert identity_resolution_service.calls == 1
    assert conversation_resolution_service.calls == 1
    assert conversation_resolution_service.customer_ids == [CUSTOMER_ID]


def test_post_webhook_rejects_malformed_payload_after_valid_signature(monkeypatch) -> None:
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


def test_post_webhook_rejects_unresolved_organization_after_valid_signature(monkeypatch) -> None:
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
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-app-secret")
    identity_resolution_service = RecordingWhatsAppCustomerIdentityResolutionService()
    app.dependency_overrides[get_whatsapp_organization_resolution_service] = (
        lambda: AcceptingWhatsAppOrganizationResolutionService()
    )
    app.dependency_overrides[get_whatsapp_customer_identity_resolution_service] = (
        lambda: identity_resolution_service
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


def test_post_webhook_skips_conversation_resolution_without_customer_id(
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

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert identity_resolution_service.calls == 1
    assert conversation_resolution_service.calls == 0


def test_post_webhook_rejects_invalid_signature(monkeypatch) -> None:
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

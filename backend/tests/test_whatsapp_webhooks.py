from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.whatsapp_signature import build_meta_signature


client = TestClient(app)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    signature = build_meta_signature(raw_body, settings.whatsapp_app_secret)

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


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

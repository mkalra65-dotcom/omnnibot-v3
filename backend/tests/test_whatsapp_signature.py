from app.services.whatsapp_signature import (
    build_meta_signature,
    validate_meta_signature,
)


def test_validate_meta_signature_accepts_valid_signature() -> None:
    raw_body = b'{"object":"whatsapp_business_account"}'
    app_secret = "test-app-secret"
    signature = build_meta_signature(raw_body, app_secret)

    assert validate_meta_signature(
        raw_body=raw_body,
        signature_header=signature,
        app_secret=app_secret,
    )


def test_validate_meta_signature_rejects_tampered_body() -> None:
    app_secret = "test-app-secret"
    signature = build_meta_signature(b'{"ok":true}', app_secret)

    assert not validate_meta_signature(
        raw_body=b'{"ok":false}',
        signature_header=signature,
        app_secret=app_secret,
    )


def test_validate_meta_signature_rejects_missing_secret_or_header() -> None:
    raw_body = b"{}"
    signature = build_meta_signature(raw_body, "test-app-secret")

    assert not validate_meta_signature(
        raw_body=raw_body,
        signature_header=signature,
        app_secret="",
    )
    assert not validate_meta_signature(
        raw_body=raw_body,
        signature_header=None,
        app_secret="test-app-secret",
    )


def test_validate_meta_signature_rejects_wrong_scheme() -> None:
    assert not validate_meta_signature(
        raw_body=b"{}",
        signature_header="sha1=abc123",
        app_secret="test-app-secret",
    )

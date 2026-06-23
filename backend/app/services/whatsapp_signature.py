import hashlib
import hmac


META_SIGNATURE_PREFIX = "sha256="


def build_meta_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"{META_SIGNATURE_PREFIX}{digest}"


def validate_meta_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    if not app_secret or not signature_header:
        return False

    if not signature_header.startswith(META_SIGNATURE_PREFIX):
        return False

    expected_signature = build_meta_signature(raw_body, app_secret)
    return hmac.compare_digest(signature_header, expected_signature)

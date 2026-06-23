from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class MetaWhatsAppPayloadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MetaWhatsAppInboundMessage:
    external_message_id: str | None
    from_wa_id: str | None
    message_type: str | None
    body: str | None
    external_created_at: datetime | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MetaWhatsAppWebhookPayload:
    phone_number_id: str
    whatsapp_business_account_id: str | None
    wa_ids: tuple[str, ...]
    has_inbound_messages: bool
    event_type: str
    external_event_id: str | None
    provider_metadata: dict[str, Any]
    inbound_messages: tuple[MetaWhatsAppInboundMessage, ...] = ()


def parse_meta_whatsapp_webhook(raw_body: bytes) -> MetaWhatsAppWebhookPayload:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise MetaWhatsAppPayloadError("Malformed Meta WhatsApp webhook payload") from exc

    if not isinstance(payload, dict):
        raise MetaWhatsAppPayloadError("Meta WhatsApp webhook payload must be an object")
    if payload.get("object") != "whatsapp_business_account":
        raise MetaWhatsAppPayloadError("Unsupported Meta webhook object")

    phone_number_ids: set[str] = set()
    whatsapp_business_account_ids: set[str] = set()
    display_phone_numbers: set[str] = set()
    fields: set[str] = set()
    messaging_products: set[str] = set()
    wa_ids: set[str] = set()
    message_ids: set[str] = set()
    status_ids: set[str] = set()
    has_inbound_messages = False
    inbound_messages: list[MetaWhatsAppInboundMessage] = []

    for entry in _list(payload.get("entry")):
        entry_id = _optional_str(entry.get("id"))
        if entry_id:
            whatsapp_business_account_ids.add(entry_id)

        for change in _list(entry.get("changes")):
            field = _optional_str(change.get("field"))
            if field:
                fields.add(field)

            value = change.get("value")
            if not isinstance(value, dict):
                continue

            messaging_product = _optional_str(value.get("messaging_product"))
            if messaging_product:
                messaging_products.add(messaging_product)

            messages = _list(value.get("messages"))
            if messages:
                has_inbound_messages = True
            for message in messages:
                message_id = _optional_str(message.get("id"))
                if message_id:
                    message_ids.add(message_id)
                inbound_messages.append(_parse_inbound_message(message))

            for status in _list(value.get("statuses")):
                status_id = _optional_str(status.get("id"))
                if status_id:
                    status_ids.add(status_id)

            for contact in _list(value.get("contacts")):
                wa_id = _optional_str(contact.get("wa_id"))
                if wa_id:
                    wa_ids.add(wa_id)

            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue

            phone_number_id = _optional_str(metadata.get("phone_number_id"))
            if phone_number_id:
                phone_number_ids.add(phone_number_id)

            display_phone_number = _optional_str(metadata.get("display_phone_number"))
            if display_phone_number:
                display_phone_numbers.add(display_phone_number)

    if not phone_number_ids:
        raise MetaWhatsAppPayloadError("Meta WhatsApp payload is missing phone_number_id")
    if len(phone_number_ids) > 1:
        raise MetaWhatsAppPayloadError("Meta WhatsApp payload contains multiple phone_number_id values")
    if len(whatsapp_business_account_ids) > 1:
        raise MetaWhatsAppPayloadError(
            "Meta WhatsApp payload contains multiple whatsapp_business_account_id values"
        )

    return MetaWhatsAppWebhookPayload(
        phone_number_id=next(iter(phone_number_ids)),
        whatsapp_business_account_id=(
            next(iter(whatsapp_business_account_ids)) if whatsapp_business_account_ids else None
        ),
        wa_ids=tuple(sorted(wa_ids)),
        has_inbound_messages=has_inbound_messages,
        event_type=_resolve_event_type(has_inbound_messages, status_ids),
        external_event_id=_resolve_external_event_id(message_ids, status_ids),
        provider_metadata={
            "provider": "whatsapp",
            "source": "meta",
            "object": payload.get("object"),
            "fields": sorted(fields),
            "messaging_products": sorted(messaging_products),
            "display_phone_numbers": sorted(display_phone_numbers),
        },
        inbound_messages=tuple(inbound_messages),
    )


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _parse_inbound_message(message: dict[str, Any]) -> MetaWhatsAppInboundMessage:
    message_type = _optional_str(message.get("type"))
    external_message_id = _optional_str(message.get("id"))
    from_wa_id = _optional_str(message.get("from"))
    external_created_at = _parse_meta_timestamp(message.get("timestamp"))
    body = _message_body(message, message_type)
    metadata = {
        "provider": "whatsapp",
        "source": "meta",
        "from": from_wa_id,
        "message_type": message_type,
    }
    media_metadata = _media_metadata(message, message_type)
    if media_metadata:
        metadata["media"] = media_metadata
    if message_type not in {"text", "image", "document", "audio"}:
        metadata["unsupported_message_type"] = message_type

    return MetaWhatsAppInboundMessage(
        external_message_id=external_message_id,
        from_wa_id=from_wa_id,
        message_type=message_type,
        body=body,
        external_created_at=external_created_at,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _message_body(message: dict[str, Any], message_type: str | None) -> str | None:
    if message_type != "text":
        return None
    text = message.get("text")
    if not isinstance(text, dict):
        return None
    return _optional_str(text.get("body"))


def _media_metadata(message: dict[str, Any], message_type: str | None) -> dict[str, Any]:
    if message_type not in {"image", "document", "audio"}:
        return {}
    media = message.get(message_type)
    if not isinstance(media, dict):
        return {}

    allowed_keys = ("id", "mime_type", "sha256", "filename", "caption", "voice")
    return {
        key: media[key]
        for key in allowed_keys
        if key in media and isinstance(media[key], (str, bool))
    }


def _parse_meta_timestamp(value: Any) -> datetime | None:
    timestamp = _optional_str(value)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (OverflowError, ValueError):
        return None


def _resolve_event_type(has_inbound_messages: bool, status_ids: set[str]) -> str:
    if has_inbound_messages:
        return "message"
    if status_ids:
        return "status"
    return "unknown"


def _resolve_external_event_id(message_ids: set[str], status_ids: set[str]) -> str | None:
    ids = message_ids or status_ids
    if len(ids) != 1:
        return None
    return next(iter(ids))

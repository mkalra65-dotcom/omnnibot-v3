from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class MetaWhatsAppPayloadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MetaWhatsAppWebhookPayload:
    phone_number_id: str
    whatsapp_business_account_id: str | None
    wa_ids: tuple[str, ...]
    has_inbound_messages: bool
    provider_metadata: dict[str, Any]


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
    has_inbound_messages = False

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

            if _list(value.get("messages")):
                has_inbound_messages = True

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
        provider_metadata={
            "provider": "whatsapp",
            "source": "meta",
            "object": payload.get("object"),
            "fields": sorted(fields),
            "messaging_products": sorted(messaging_products),
            "display_phone_numbers": sorted(display_phone_numbers),
        },
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

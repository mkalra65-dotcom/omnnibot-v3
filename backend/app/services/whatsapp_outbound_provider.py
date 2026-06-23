from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings


class WhatsAppOutboundProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, response_payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.response_payload = response_payload or {}


class WhatsAppOutboundProviderTimeout(WhatsAppOutboundProviderError):
    pass


@dataclass(frozen=True, slots=True)
class WhatsAppOutboundSendRequest:
    phone_number_id: str
    access_token: str
    to_wa_id: str
    body: str


@dataclass(frozen=True, slots=True)
class WhatsAppOutboundSendResult:
    external_message_id: str
    provider_response: dict[str, Any] = field(default_factory=dict)


class WhatsAppOutboundProvider:
    def send_text(self, payload: WhatsAppOutboundSendRequest) -> WhatsAppOutboundSendResult:
        raise NotImplementedError


class MetaWhatsAppOutboundProvider(WhatsAppOutboundProvider):
    def __init__(self, *, graph_api_version: str | None = None, timeout_seconds: float = 10.0) -> None:
        self.graph_api_version = (graph_api_version or settings.whatsapp_graph_api_version).strip()
        self.timeout_seconds = timeout_seconds

    def send_text(self, payload: WhatsAppOutboundSendRequest) -> WhatsAppOutboundSendResult:
        url = f"https://graph.facebook.com/{self.graph_api_version}/{payload.phone_number_id}/messages"
        request_body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": payload.to_wa_id,
            "type": "text",
            "text": {"preview_url": False, "body": payload.body},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {payload.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except socket.timeout as exc:
            raise WhatsAppOutboundProviderTimeout("meta_timeout", "Meta WhatsApp request timed out") from exc
        except urllib.error.HTTPError as exc:
            response_payload = _read_error_payload(exc)
            error = response_payload.get("error") if isinstance(response_payload.get("error"), dict) else {}
            raise WhatsAppOutboundProviderError(
                str(error.get("code") or "meta_api_error"),
                str(error.get("message") or "Meta WhatsApp API rejected the message"),
                response_payload=response_payload,
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise WhatsAppOutboundProviderTimeout("meta_timeout", "Meta WhatsApp request timed out") from exc
            raise WhatsAppOutboundProviderError("meta_network_error", "Meta WhatsApp request failed") from exc
        except json.JSONDecodeError as exc:
            raise WhatsAppOutboundProviderError(
                "meta_malformed_response",
                "Meta WhatsApp API returned malformed JSON",
            ) from exc

        message_id = _extract_message_id(response_payload)
        if message_id is None:
            raise WhatsAppOutboundProviderError(
                "meta_missing_message_id",
                "Meta WhatsApp API response did not include a message id",
                response_payload=response_payload,
            )

        return WhatsAppOutboundSendResult(
            external_message_id=message_id,
            provider_response=_safe_provider_response(response_payload),
        )


def _read_error_payload(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        return json.loads(exc.read().decode("utf-8"))
    except Exception:
        return {}


def _extract_message_id(payload: dict[str, Any]) -> str | None:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict):
        return None
    message_id = first.get("id")
    return message_id if isinstance(message_id, str) and message_id.strip() else None


def _safe_provider_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "messaging_product": payload.get("messaging_product"),
        "contacts": payload.get("contacts") if isinstance(payload.get("contacts"), list) else [],
        "messages": payload.get("messages") if isinstance(payload.get("messages"), list) else [],
    }

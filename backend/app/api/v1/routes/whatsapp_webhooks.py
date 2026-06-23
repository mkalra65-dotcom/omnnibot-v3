import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from postgrest.exceptions import APIError

from app.core.config import settings
from app.core.supabase import get_supabase_factory
from app.db.models.records import WebhookEventCreate
from app.db.repositories.webhook_event_repository import WebhookEventRepository
from app.services.whatsapp_customer_identity_resolution import (
    WhatsAppCustomerIdentityInputError,
    WhatsAppCustomerIdentityResolutionError,
    WhatsAppCustomerIdentityResolutionService,
)
from app.services.whatsapp_conversation_resolution import (
    WhatsAppConversationInputError,
    WhatsAppConversationResolutionService,
)
from app.services.whatsapp_message_persistence import WhatsAppMessagePersistenceService
from app.services.whatsapp_organization_resolution import (
    WhatsAppOrganizationResolutionError,
    WhatsAppOrganizationResolutionService,
)
from app.services.whatsapp_payloads import MetaWhatsAppPayloadError, parse_meta_whatsapp_webhook
from app.services.whatsapp_signature import validate_meta_signature

router = APIRouter()


def get_whatsapp_organization_resolution_service() -> WhatsAppOrganizationResolutionService:
    return WhatsAppOrganizationResolutionService()


def get_whatsapp_customer_identity_resolution_service() -> WhatsAppCustomerIdentityResolutionService:
    return WhatsAppCustomerIdentityResolutionService()


def get_whatsapp_conversation_resolution_service() -> WhatsAppConversationResolutionService:
    return WhatsAppConversationResolutionService()


def get_whatsapp_message_persistence_service() -> WhatsAppMessagePersistenceService:
    return WhatsAppMessagePersistenceService()


def get_webhook_event_repository() -> WebhookEventRepository:
    return WebhookEventRepository(get_supabase_factory().get_service_client())


@router.get("")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    token_is_valid = (
        bool(settings.whatsapp_verify_token)
        and hub_mode == "subscribe"
        and hmac.compare_digest(hub_verify_token, settings.whatsapp_verify_token)
    )
    if not token_is_valid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return Response(content=hub_challenge, media_type="text/plain")


@router.post("")
async def receive_whatsapp_webhook(
    request: Request,
    organization_resolution_service: WhatsAppOrganizationResolutionService = Depends(
        get_whatsapp_organization_resolution_service
    ),
    customer_identity_resolution_service: WhatsAppCustomerIdentityResolutionService = Depends(
        get_whatsapp_customer_identity_resolution_service
    ),
    conversation_resolution_service: WhatsAppConversationResolutionService = Depends(
        get_whatsapp_conversation_resolution_service
    ),
    message_persistence_service: WhatsAppMessagePersistenceService = Depends(
        get_whatsapp_message_persistence_service
    ),
    webhook_event_repository: WebhookEventRepository = Depends(get_webhook_event_repository),
) -> dict[str, str | bool | None]:
    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")

    if not validate_meta_signature(
        raw_body=raw_body,
        signature_header=signature_header,
        app_secret=settings.whatsapp_app_secret,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        payload = parse_meta_whatsapp_webhook(raw_body)
        organization_resolution = organization_resolution_service.resolve(payload)
        webhook_event_created = _persist_webhook_event(
            repository=webhook_event_repository,
            payload=payload,
            organization_resolution=organization_resolution,
            raw_body=raw_body,
            request=request,
        )
        if payload.has_inbound_messages and payload.wa_ids:
            customer_identity_resolution = customer_identity_resolution_service.resolve(
                payload=payload,
                organization_resolution=organization_resolution,
            )
            if customer_identity_resolution.customer_id is not None:
                conversation_resolution = conversation_resolution_service.resolve(
                    customer_identity_resolution
                )
                message_persistence_service.persist_inbound(
                    payload=payload,
                    organization_resolution=organization_resolution,
                    customer_identity_resolution=customer_identity_resolution,
                    conversation_resolution=conversation_resolution,
                    webhook_delivery_id=webhook_event_created.delivery_id,
                )
    except MetaWhatsAppPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed WhatsApp webhook payload",
        ) from exc
    except WhatsAppCustomerIdentityInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed WhatsApp customer identity",
        ) from exc
    except WhatsAppConversationInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed WhatsApp conversation resolution",
        ) from exc
    except WhatsAppOrganizationResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    except WhatsAppCustomerIdentityResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer identity conflict") from exc

    return {"status": "accepted"}


@dataclass(frozen=True, slots=True)
class WebhookEventPersistenceResult:
    created: bool
    delivery_id: str | None


def _persist_webhook_event(
    *,
    repository: WebhookEventRepository,
    payload,
    organization_resolution,
    raw_body: bytes,
    request: Request,
) -> WebhookEventPersistenceResult:
    provider = "whatsapp"
    payload_hash = sha256(raw_body).hexdigest()
    delivery_id = _resolve_delivery_id(request=request, payload_hash=payload_hash)

    if delivery_id is not None and repository.get_by_delivery_id(provider, delivery_id) is not None:
        return WebhookEventPersistenceResult(created=False, delivery_id=delivery_id)
    if (
        payload.external_event_id is not None
        and repository.get_by_external_event_id(provider, payload.external_event_id) is not None
    ):
        return WebhookEventPersistenceResult(created=False, delivery_id=delivery_id)

    event = WebhookEventCreate(
        provider=provider,
        event_type=payload.event_type,
        delivery_id=delivery_id,
        external_event_id=payload.external_event_id,
        organization_id=organization_resolution.organization_id,
        account_id=organization_resolution.account_id,
        phone_number_id=organization_resolution.phone_number_id,
        signature_valid=True,
        resolved=True,
        payload_hash=payload_hash,
        payload=None,
        metadata={
            "source": "meta",
            "whatsapp_business_account_id": payload.whatsapp_business_account_id,
        },
        received_at=datetime.now(timezone.utc),
    )
    try:
        repository.create(event)
    except APIError as exc:
        if _is_unique_violation(exc):
            return WebhookEventPersistenceResult(created=False, delivery_id=delivery_id)
        raise
    return WebhookEventPersistenceResult(created=True, delivery_id=delivery_id)


def _resolve_delivery_id(*, request: Request, payload_hash: str) -> str:
    for header_name in ("X-Hub-Delivery", "X-Meta-Delivery-ID"):
        header_value = request.headers.get(header_name)
        if header_value and header_value.strip():
            return header_value.strip()
    return f"meta:{payload_hash}"


def _is_unique_violation(exc: APIError) -> bool:
    return exc.json().get("code") == "23505"

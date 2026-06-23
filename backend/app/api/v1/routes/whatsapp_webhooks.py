import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.core.config import settings
from app.services.whatsapp_customer_identity_resolution import (
    WhatsAppCustomerIdentityInputError,
    WhatsAppCustomerIdentityResolutionError,
    WhatsAppCustomerIdentityResolutionService,
)
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
        if payload.has_inbound_messages and payload.wa_ids:
            customer_identity_resolution_service.resolve(
                payload=payload,
                organization_resolution=organization_resolution,
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
    except WhatsAppOrganizationResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    except WhatsAppCustomerIdentityResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer identity conflict") from exc

    return {"status": "accepted"}

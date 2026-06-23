import hmac

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.config import settings
from app.services.whatsapp_signature import validate_meta_signature

router = APIRouter()


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
async def receive_whatsapp_webhook(request: Request) -> dict[str, str]:
    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")

    if not validate_meta_signature(
        raw_body=raw_body,
        signature_header=signature_header,
        app_secret=settings.whatsapp_app_secret,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return {"status": "accepted"}

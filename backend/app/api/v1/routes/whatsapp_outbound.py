from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_tenant_context
from app.schemas.whatsapp_outbound import WhatsAppReviewSendRequest, WhatsAppReviewSendResponse
from app.services.organization_access import TenantContext
from app.services.whatsapp_outbound_send import WhatsAppOutboundSendService

router = APIRouter()


def get_whatsapp_outbound_send_service() -> WhatsAppOutboundSendService:
    return WhatsAppOutboundSendService()


@router.post("/reviews/{review_id}/send", response_model=WhatsAppReviewSendResponse)
async def send_approved_review(
    review_id: UUID,
    payload: WhatsAppReviewSendRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: WhatsAppOutboundSendService = Depends(get_whatsapp_outbound_send_service),
) -> WhatsAppReviewSendResponse:
    result = service.send_review(
        tenant,
        review_id,
        send_idempotency_key=payload.send_idempotency_key,
    )
    return result.as_response()

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.base import ApiModel


class WhatsAppReviewSendRequest(ApiModel):
    send_idempotency_key: str


class WhatsAppReviewSendResponse(ApiModel):
    review_id: UUID
    message_id: UUID | None = None
    external_message_id: str | None = None
    status: str
    sent_at: datetime | None = None
    idempotent: bool = False

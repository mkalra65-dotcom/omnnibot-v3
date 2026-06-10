from uuid import UUID

from app.db.models.common import ChannelType
from app.db.models.records import MessageRead
from app.schemas.base import ApiModel


class MessageCreateRequest(ApiModel):
    conversation_id: UUID
    customer_id: UUID | None = None
    channel: ChannelType
    direction: str
    sender_type: str
    sender_user_id: UUID | None = None
    external_message_id: str | None = None
    external_event_id: str | None = None
    webhook_delivery_id: str | None = None
    message_type: str = "text"
    body: str | None = None
    media_url: str | None = None


class MessageListResponse(ApiModel):
    items: list[MessageRead]
    total: int
    page: int
    page_size: int
    offset: int
    limit: int

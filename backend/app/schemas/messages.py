from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class MessageBase(TimestampedModel):
    organization_id: UUID
    conversation_id: UUID
    customer_id: UUID | None = None
    channel: str = "whatsapp"
    direction: str
    sender_type: str
    message_type: str = "text"
    body: str | None = None
    provider_message_id: str | None = None
    status: str = "received"
    metadata: JsonDict = Field(default_factory=dict)


class MessageCreate(MessageBase):
    pass


class MessageUpdate(TimestampedModel):
    status: str | None = None
    metadata: JsonDict | None = None


class MessageRead(MessageBase):
    id: UUID

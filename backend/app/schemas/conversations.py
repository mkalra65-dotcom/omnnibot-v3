from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class ConversationBase(TimestampedModel):
    organization_id: UUID
    customer_id: UUID
    channel: str = "whatsapp"
    status: str = "open"
    assigned_user_id: UUID | None = None
    metadata: JsonDict = Field(default_factory=dict)


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(TimestampedModel):
    status: str | None = None
    assigned_user_id: UUID | None = None
    metadata: JsonDict | None = None


class ConversationRead(ConversationBase):
    id: UUID

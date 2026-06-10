from datetime import datetime
from uuid import UUID

from app.db.models.common import ChannelType, ConversationStatus
from app.db.models.records import ConversationRead
from app.schemas.base import ApiModel


class ConversationCreateRequest(ApiModel):
    customer_id: UUID
    channel: ChannelType = ChannelType.MANUAL
    external_conversation_id: str | None = None
    status: ConversationStatus = ConversationStatus.OPEN
    priority: str = "normal"
    assigned_membership_id: UUID | None = None
    summary: str | None = None


class ConversationUpdateRequest(ApiModel):
    status: ConversationStatus | None = None
    priority: str | None = None
    assigned_membership_id: UUID | None = None
    summary: str | None = None


class HandoffStatusUpdate(ApiModel):
    handoff_status: str


class FollowupTimestampsUpdate(ApiModel):
    last_ai_response_at: datetime | None = None
    last_customer_response_at: datetime | None = None


class ConversationListResponse(ApiModel):
    items: list[ConversationRead]
    total: int
    page: int
    page_size: int
    offset: int
    limit: int

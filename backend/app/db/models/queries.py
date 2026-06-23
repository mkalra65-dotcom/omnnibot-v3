from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.db.models.common import (
    BasePayload,
    ChannelType,
    ConversationStatus,
    CustomerStatus,
    FaqStatus,
    LeadStage,
    MessageStatus,
    OrganizationStatus,
    ProductStatus,
    SortDirection,
    TimestampRange,
    WebhookEventStatus,
    WhatsAppAccountStatus,
)


class BaseListFilters(TimestampRange):
    status: str | None = None


class OrganizationFilters(BaseListFilters):
    status: OrganizationStatus | None = None


class CustomerFilters(BaseListFilters):
    status: CustomerStatus | None = None
    lead_stage: LeadStage | None = None
    min_lead_score: float | None = None
    max_lead_score: float | None = None
    min_lifetime_value: float | None = None
    max_lifetime_value: float | None = None


class ConversationFilters(BaseListFilters):
    status: ConversationStatus | None = None
    channel: ChannelType | None = None
    assigned_membership_id: UUID | None = None
    handoff_status: str | None = None


class MessageFilters(BaseListFilters):
    status: MessageStatus | None = None
    channel: ChannelType | None = None
    direction: str | None = None
    sender_type: str | None = None


class WhatsAppAccountFilters(BaseListFilters):
    status: WhatsAppAccountStatus | None = None


class WebhookEventFilters(BaseListFilters):
    status: WebhookEventStatus | None = None
    provider: str | None = None
    event_type: str | None = None
    resolved: bool | None = None
    phone_number_id: str | None = None


class ProductFilters(BaseListFilters):
    status: ProductStatus | None = None
    category: str | None = None


class FaqFilters(BaseListFilters):
    status: FaqStatus | None = None
    category: str | None = None


class LeadEventFilters(BaseListFilters):
    lead_stage: LeadStage | None = None
    event_type: str | None = None


class AiInteractionFilters(BaseListFilters):
    conversation_id: UUID | None = None
    interaction_type: str | None = None
    provider: str | None = None
    model: str | None = None


class AiDraftReviewFilters(BaseListFilters):
    conversation_id: UUID | None = None
    customer_id: UUID | None = None


class SubscriptionFilters(BaseListFilters):
    status: str | None = None
    plan_slug: str | None = None


class SortOptions(BasePayload):
    field: str = "created_at"
    direction: SortDirection = SortDirection.DESC

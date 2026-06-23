from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.db.models.common import (
    BasePayload,
    BaseIdRecord,
    BaseRecord,
    ChannelType,
    ConversationStatus,
    CustomerStatus,
    FaqStatus,
    LeadStage,
    MessageStatus,
    OrganizationStatus,
    ProductStatus,
    WebhookEventStatus,
    WhatsAppAccountStatus,
)

BaseReadModel = BaseIdRecord


class OrganizationRead(BaseIdRecord):
    name: str
    slug: str | None = None
    status: OrganizationStatus
    default_currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    settings: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class OrganizationCreate(BasePayload):
    name: str
    slug: str | None = None
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    default_currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    settings: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class OrganizationUpdate(BasePayload):
    name: str | None = None
    slug: str | None = None
    status: OrganizationStatus | None = None
    default_currency: str | None = None
    timezone: str | None = None
    settings: dict | None = None
    metadata: dict | None = None


class CustomerIdentityRead(BaseRecord):
    customer_id: UUID
    provider: str
    provider_user_id: str | None = None
    provider_username: str | None = None
    provider_phone: str | None = None
    metadata: dict = Field(default_factory=dict)


class CustomerIdentityCreate(BasePayload):
    customer_id: UUID
    provider: str
    provider_user_id: str | None = None
    provider_username: str | None = None
    provider_phone: str | None = None
    metadata: dict = Field(default_factory=dict)


class CustomerIdentityUpdate(BasePayload):
    provider_user_id: str | None = None
    provider_username: str | None = None
    provider_phone: str | None = None
    metadata: dict | None = None


class CustomerRead(BaseRecord):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    status: CustomerStatus
    lead_score: Decimal = Decimal("0")
    lead_stage: LeadStage
    purchase_stage: str
    lifetime_value_amount: Decimal = Decimal("0")
    lifetime_value_currency: str = "INR"
    order_count: int = 0
    first_purchase_at: datetime | None = None
    last_purchase_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_engaged_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    profile: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class CustomerCreate(BasePayload):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    status: CustomerStatus = CustomerStatus.LEAD
    lead_score: Decimal = Decimal("0")
    lead_stage: LeadStage = LeadStage.NEW
    purchase_stage: str = "unknown"
    lifetime_value_amount: Decimal = Decimal("0")
    lifetime_value_currency: str = "INR"
    order_count: int = 0
    first_purchase_at: datetime | None = None
    last_purchase_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_engaged_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    profile: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class CustomerUpdate(BasePayload):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    status: CustomerStatus | None = None
    lead_score: Decimal | None = None
    lead_stage: LeadStage | None = None
    purchase_stage: str | None = None
    lifetime_value_amount: Decimal | None = None
    lifetime_value_currency: str | None = None
    order_count: int | None = None
    first_purchase_at: datetime | None = None
    last_purchase_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_engaged_at: datetime | None = None
    tags: list[str] | None = None
    profile: dict | None = None
    metadata: dict | None = None


class ConversationRead(BaseRecord):
    customer_id: UUID
    channel: ChannelType
    external_conversation_id: str | None = None
    status: ConversationStatus
    handoff_status: str
    priority: str
    assigned_membership_id: UUID | None = None
    state: dict = Field(default_factory=dict)
    summary: str | None = None
    last_message_id: UUID | None = None
    last_message_at: datetime | None = None
    last_ai_response_at: datetime | None = None
    last_customer_response_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class ConversationCreate(BasePayload):
    customer_id: UUID
    channel: ChannelType
    external_conversation_id: str | None = None
    status: ConversationStatus = ConversationStatus.OPEN
    handoff_status: str = "ai"
    priority: str = "normal"
    assigned_membership_id: UUID | None = None
    state: dict = Field(default_factory=dict)
    summary: str | None = None
    last_message_id: UUID | None = None
    last_message_at: datetime | None = None
    last_ai_response_at: datetime | None = None
    last_customer_response_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class ConversationUpdate(BasePayload):
    status: ConversationStatus | None = None
    handoff_status: str | None = None
    priority: str | None = None
    assigned_membership_id: UUID | None = None
    state: dict | None = None
    summary: str | None = None
    last_message_id: UUID | None = None
    last_message_at: datetime | None = None
    last_ai_response_at: datetime | None = None
    last_customer_response_at: datetime | None = None
    closed_at: datetime | None = None
    metadata: dict | None = None


class MessageRead(BaseRecord):
    conversation_id: UUID
    customer_id: UUID | None = None
    channel: ChannelType
    direction: str
    sender_type: str
    sender_user_id: UUID | None = None
    external_message_id: str | None = None
    external_event_id: str | None = None
    webhook_delivery_id: str | None = None
    message_type: str
    body: str | None = None
    media_url: str | None = None
    status: MessageStatus
    generated_by_ai: bool = False
    sent_by_human: bool = False
    provider_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    external_created_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None


class MessageCreate(BasePayload):
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
    status: MessageStatus = MessageStatus.RECEIVED
    generated_by_ai: bool = False
    sent_by_human: bool = False
    provider_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    external_created_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None


class MessageUpdate(BasePayload):
    status: MessageStatus | None = None
    body: str | None = None
    media_url: str | None = None
    provider_payload: dict | None = None
    metadata: dict | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None


class WhatsAppAccountRead(BaseRecord):
    phone_number_id: str
    whatsapp_business_account_id: str | None = None
    display_phone_number: str | None = None
    status: WhatsAppAccountStatus
    verify_token_hash: str | None = None
    access_token_secret_ref: str | None = None
    metadata: dict = Field(default_factory=dict)


class WhatsAppAccountCreate(BasePayload):
    phone_number_id: str
    whatsapp_business_account_id: str | None = None
    display_phone_number: str | None = None
    status: WhatsAppAccountStatus = WhatsAppAccountStatus.PENDING
    verify_token_hash: str | None = None
    access_token_secret_ref: str | None = None
    metadata: dict = Field(default_factory=dict)


class WhatsAppAccountUpdate(BasePayload):
    whatsapp_business_account_id: str | None = None
    display_phone_number: str | None = None
    status: WhatsAppAccountStatus | None = None
    verify_token_hash: str | None = None
    access_token_secret_ref: str | None = None
    metadata: dict | None = None


class WebhookEventRead(BaseIdRecord):
    provider: str
    event_type: str
    delivery_id: str | None = None
    external_event_id: str | None = None
    organization_id: UUID | None = None
    account_id: UUID | None = None
    phone_number_id: str | None = None
    status: WebhookEventStatus
    signature_valid: bool | None = None
    resolved: bool = False
    error_code: str | None = None
    error_message: str | None = None
    payload_hash: str | None = None
    payload: dict | None = None
    metadata: dict = Field(default_factory=dict)
    received_at: datetime | None = None
    processed_at: datetime | None = None


class WebhookEventCreate(BasePayload):
    provider: str
    event_type: str
    delivery_id: str | None = None
    external_event_id: str | None = None
    organization_id: UUID | None = None
    account_id: UUID | None = None
    phone_number_id: str | None = None
    status: WebhookEventStatus = WebhookEventStatus.RECEIVED
    signature_valid: bool | None = None
    resolved: bool = False
    error_code: str | None = None
    error_message: str | None = None
    payload_hash: str | None = None
    payload: dict | None = None
    metadata: dict = Field(default_factory=dict)
    received_at: datetime | None = None
    processed_at: datetime | None = None


class WebhookEventUpdate(BasePayload):
    organization_id: UUID | None = None
    account_id: UUID | None = None
    phone_number_id: str | None = None
    status: WebhookEventStatus | None = None
    signature_valid: bool | None = None
    resolved: bool | None = None
    error_code: str | None = None
    error_message: str | None = None
    payload_hash: str | None = None
    payload: dict | None = None
    metadata: dict | None = None
    processed_at: datetime | None = None


class ProductRead(BaseRecord):
    name: str
    normalized_name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    material: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    currency: str
    inventory_quantity: int
    inventory_reserved: int
    inventory_low_stock_threshold: int | None = None
    track_inventory: bool = True
    image_url: str | None = None
    product_url: str | None = None
    status: ProductStatus
    attributes: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ProductCreate(BasePayload):
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    material: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    currency: str = "INR"
    inventory_quantity: int = 0
    inventory_reserved: int = 0
    inventory_low_stock_threshold: int | None = None
    track_inventory: bool = True
    image_url: str | None = None
    product_url: str | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    attributes: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ProductUpdate(BasePayload):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    material: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    currency: str | None = None
    inventory_quantity: int | None = None
    inventory_reserved: int | None = None
    inventory_low_stock_threshold: int | None = None
    track_inventory: bool | None = None
    image_url: str | None = None
    product_url: str | None = None
    status: ProductStatus | None = None
    attributes: dict | None = None
    metadata: dict | None = None


class FaqRead(BaseRecord):
    question: str
    normalized_question: str
    answer: str
    category: str | None = None
    status: FaqStatus
    usage_count: int = 0
    last_used_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class FaqCreate(BasePayload):
    question: str
    answer: str
    category: str | None = None
    status: FaqStatus = FaqStatus.ACTIVE
    usage_count: int = 0
    last_used_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class FaqUpdate(BasePayload):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    status: FaqStatus | None = None
    usage_count: int | None = None
    last_used_at: datetime | None = None
    metadata: dict | None = None


class LeadEventRead(BaseRecord):
    customer_id: UUID
    conversation_id: UUID | None = None
    lead_stage: LeadStage
    event_type: str
    metadata: dict = Field(default_factory=dict)


class LeadEventCreate(BasePayload):
    customer_id: UUID
    conversation_id: UUID | None = None
    lead_stage: LeadStage
    event_type: str
    metadata: dict = Field(default_factory=dict)


class AiInteractionRead(BaseRecord):
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    interaction_type: str
    status: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int | None = None
    cost_estimate: Decimal = Decimal("0")
    request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict = Field(default_factory=dict)


class AiInteractionCreate(BasePayload):
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    interaction_type: str
    status: str = "success"
    provider: str = "openai"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int | None = None
    cost_estimate: Decimal = Decimal("0")
    request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict = Field(default_factory=dict)


class AiDraftReviewRead(BaseRecord):
    conversation_id: UUID
    customer_id: UUID | None = None
    source_message_id: UUID | None = None
    ai_interaction_id: UUID | None = None
    draft_text: str
    edited_text: str | None = None
    status: str
    approved_by_membership_id: UUID | None = None
    rejected_by_membership_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class AiDraftReviewCreate(BasePayload):
    conversation_id: UUID
    customer_id: UUID | None = None
    source_message_id: UUID | None = None
    ai_interaction_id: UUID | None = None
    draft_text: str
    edited_text: str | None = None
    status: str = "pending"
    approved_by_membership_id: UUID | None = None
    rejected_by_membership_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class AiDraftReviewUpdate(BasePayload):
    edited_text: str | None = None
    status: str | None = None
    approved_by_membership_id: UUID | None = None
    rejected_by_membership_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    metadata: dict | None = None


class SubscriptionPlanRead(BaseIdRecord):
    name: str
    slug: str
    status: str
    monthly_message_limit: int
    monthly_ai_request_limit: int
    monthly_token_limit: int
    metadata: dict = Field(default_factory=dict)


class OrganizationSubscriptionRead(BaseRecord):
    subscription_plan_id: UUID
    status: str
    current_period_start: date
    current_period_end: date
    metadata: dict = Field(default_factory=dict)


class SubscriptionPlanLimits(BasePayload):
    subscription_plan_id: UUID
    subscription_plan_name: str
    subscription_plan_slug: str
    monthly_message_limit: int
    monthly_ai_request_limit: int
    monthly_token_limit: int

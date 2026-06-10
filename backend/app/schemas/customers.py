from decimal import Decimal

from pydantic import Field

from app.db.models.common import CustomerStatus, LeadStage
from app.db.models.records import CustomerIdentityRead, CustomerRead
from app.schemas.base import ApiModel


class CustomerCreateRequest(ApiModel):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    status: CustomerStatus = CustomerStatus.LEAD
    tags: list[str] = Field(default_factory=list)
    profile: dict = Field(default_factory=dict)


class CustomerUpdateRequest(ApiModel):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    status: CustomerStatus | None = None
    tags: list[str] | None = None
    profile: dict | None = None
    lead_stage: LeadStage | None = None
    lead_score: Decimal | None = None


class CustomerIdentityCreateRequest(ApiModel):
    provider: str
    provider_user_id: str | None = None
    provider_username: str | None = None
    provider_phone: str | None = None


class CustomerListResponse(ApiModel):
    items: list[CustomerRead]
    total: int
    page: int
    page_size: int
    offset: int
    limit: int

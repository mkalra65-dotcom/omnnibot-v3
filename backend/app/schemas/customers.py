from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class CustomerBase(TimestampedModel):
    organization_id: UUID
    full_name: str | None = None
    phone_number: str | None = None
    whatsapp_user_id: str | None = None
    instagram_handle: str | None = None
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    metadata: JsonDict = Field(default_factory=dict)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(TimestampedModel):
    full_name: str | None = None
    phone_number: str | None = None
    whatsapp_user_id: str | None = None
    instagram_handle: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    metadata: JsonDict | None = None


class CustomerRead(CustomerBase):
    id: UUID

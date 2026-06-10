from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class OrganizationBase(TimestampedModel):
    name: str
    slug: str | None = None
    status: str = "active"
    metadata: JsonDict = Field(default_factory=dict)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(TimestampedModel):
    name: str | None = None
    slug: str | None = None
    status: str | None = None
    metadata: JsonDict | None = None


class OrganizationRead(OrganizationBase):
    id: UUID

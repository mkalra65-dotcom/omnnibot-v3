from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class FaqEntryBase(TimestampedModel):
    organization_id: UUID
    question: str
    answer: str
    category: str | None = None
    status: str = "active"
    metadata: JsonDict = Field(default_factory=dict)


class FaqEntryCreate(FaqEntryBase):
    pass


class FaqEntryUpdate(TimestampedModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    status: str | None = None
    metadata: JsonDict | None = None


class FaqEntryRead(FaqEntryBase):
    id: UUID

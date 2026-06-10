from uuid import UUID

from app.schemas.base import TimestampedModel


class MembershipBase(TimestampedModel):
    organization_id: UUID
    user_id: UUID
    role: str = "owner"
    status: str = "active"


class MembershipCreate(MembershipBase):
    pass


class MembershipUpdate(TimestampedModel):
    role: str | None = None
    status: str | None = None


class MembershipRead(MembershipBase):
    id: UUID

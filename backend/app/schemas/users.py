from uuid import UUID

from pydantic import EmailStr
from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class UserBase(TimestampedModel):
    email: EmailStr
    full_name: str | None = None
    avatar_url: str | None = None
    metadata: JsonDict = Field(default_factory=dict)


class UserCreate(UserBase):
    id: UUID


class UserRead(UserBase):
    id: UUID

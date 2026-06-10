from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import ApiModel


class SignupRequest(ApiModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    organization_name: str


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class AuthOrganization(ApiModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str | None = None
    membership_id: UUID
    role: str
    status: str


class AuthResponse(ApiModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: UUID
    organizations: list[AuthOrganization] = Field(default_factory=list)


class AuthUser(ApiModel):
    user_id: UUID
    email: EmailStr | None = None

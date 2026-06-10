from pydantic import EmailStr

from app.schemas.base import ApiModel


class SignupRequest(ApiModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    organization_name: str


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class AuthResponse(ApiModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"

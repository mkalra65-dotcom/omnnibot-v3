from fastapi import APIRouter, Depends

from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest
from app.services.auth import AuthService

router = APIRouter()


def get_auth_service() -> AuthService:
    return AuthService()


@router.post("/signup", response_model=AuthResponse)
async def signup(
    payload: SignupRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    return await service.signup(payload)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    return await service.login(payload)

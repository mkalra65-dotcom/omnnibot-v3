from fastapi import APIRouter, Depends

from app.schemas.auth import LoginRequest, SignupRequest
from app.services.auth import AuthService

router = APIRouter()


def get_auth_service() -> AuthService:
    return AuthService()


@router.post("/signup", status_code=501)
async def signup(
    payload: SignupRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.signup(payload)


@router.post("/login", status_code=501)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.login(payload)

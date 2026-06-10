from app.schemas.auth import LoginRequest, SignupRequest
from app.services.base import BaseService


class AuthService(BaseService):
    async def signup(self, payload: SignupRequest) -> None:
        self.not_implemented("Signup business logic is not implemented yet")

    async def login(self, payload: LoginRequest) -> None:
        self.not_implemented("Login business logic is not implemented yet")

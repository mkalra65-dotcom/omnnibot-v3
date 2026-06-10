from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import AuthUser
from app.services.auth import AuthService
from app.services.organization_access import OrganizationAccessService, TenantContext


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    return AuthService()


def get_organization_access_service() -> OrganizationAccessService:
    return OrganizationAccessService()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token is required",
        )
    return await auth_service.get_user_from_token(credentials.credentials)


async def get_tenant_context(
    x_organization_id: UUID | None = Header(default=None, alias="X-Organization-ID"),
    current_user: AuthUser = Depends(get_current_user),
    organization_access_service: OrganizationAccessService = Depends(get_organization_access_service),
) -> TenantContext:
    if x_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-ID header is required for organization-scoped routes",
        )
    return await organization_access_service.resolve_tenant_context(
        user_id=current_user.user_id,
        organization_id=x_organization_id,
    )

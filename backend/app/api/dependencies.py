from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID


async def get_tenant_context(
    x_organization_id: UUID | None = Header(default=None, alias="X-Organization-ID"),
) -> TenantContext:
    if x_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-ID header is required for tenant-scoped routes",
        )
    return TenantContext(organization_id=x_organization_id)

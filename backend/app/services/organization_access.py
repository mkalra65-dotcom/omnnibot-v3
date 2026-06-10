from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.services.base import BaseService


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    role: str


class OrganizationAccessService(BaseService):
    def __init__(self, supabase_factory: SupabaseClientFactory | None = None) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        self.service_client = self.supabase_factory.get_service_client()

    async def resolve_tenant_context(self, user_id: UUID, organization_id: UUID) -> TenantContext:
        membership = self.get_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        return TenantContext(
            organization_id=organization_id,
            user_id=user_id,
            membership_id=UUID(str(membership["id"])),
            role=membership["role"],
        )

    def get_active_membership(self, user_id: UUID, organization_id: UUID) -> dict[str, Any]:
        response = (
            self.service_client.table("memberships")
            .select("id, organization_id, user_id, role, status")
            .eq("organization_id", str(organization_id))
            .eq("user_id", str(user_id))
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not an active member of this organization",
            )
        return rows[0]

    def require_role(
        self,
        user_id: UUID,
        organization_id: UUID,
        allowed_roles: set[str],
    ) -> dict[str, Any]:
        membership = self.get_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        if membership["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User role is not allowed for this organization action",
            )
        return membership

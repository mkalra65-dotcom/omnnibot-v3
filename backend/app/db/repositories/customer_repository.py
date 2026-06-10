from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import LeadStage, PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import CustomerFilters, SortOptions
from app.db.models.records import CustomerCreate, CustomerIdentityRead, CustomerRead, CustomerUpdate
from app.db.repositories.base_repository import BaseRepository


class CustomerRepository(BaseRepository[CustomerRead, CustomerCreate, CustomerUpdate, CustomerFilters]):
    table_name = "customers"
    read_model = CustomerRead
    sortable_fields = {"created_at", "updated_at", "lead_score", "lifetime_value_amount", "last_engaged_at"}
    sort_aliases = {"lifetime_value": "lifetime_value_amount"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def get_by_id(self, organization_id: UUID, record_id: UUID, include_deleted: bool = False) -> CustomerRead | None:
        return super().get_by_id(organization_id, record_id, include_deleted=include_deleted)

    def create(self, organization_id: UUID, payload: CustomerCreate | dict[str, Any]) -> CustomerRead:
        return super().create(organization_id, payload)

    def update(
        self,
        organization_id: UUID,
        record_id: UUID,
        payload: CustomerUpdate | dict[str, Any],
        include_deleted: bool = False,
    ) -> CustomerRead | None:
        return super().update(organization_id, record_id, payload, include_deleted=include_deleted)

    def list_by_organization(
        self,
        organization_id: UUID,
        filters: CustomerFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def list_by_lead_stage(
        self,
        organization_id: UUID,
        lead_stage: LeadStage,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        filters = CustomerFilters(lead_stage=lead_stage)
        return self.list_by_organization(organization_id, filters=filters, pagination=pagination, sort=sort)

    def update_lead_score(
        self,
        organization_id: UUID,
        record_id: UUID,
        lead_score: float,
    ) -> CustomerRead | None:
        return self.update(organization_id, record_id, {"lead_score": lead_score})

    def update_lead_stage(
        self,
        organization_id: UUID,
        record_id: UUID,
        lead_stage: LeadStage,
    ) -> CustomerRead | None:
        return self.update(organization_id, record_id, {"lead_stage": lead_stage})

    def find_by_identity(
        self,
        organization_id: UUID,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
    ) -> CustomerRead | None:
        if provider_user_id is None and provider_username is None and provider_phone is None:
            return None
        identity = self._find_identity(
            organization_id=organization_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_username=provider_username,
            provider_phone=provider_phone,
        )
        if identity is None:
            return None
        return self.get_by_id(organization_id, identity.customer_id)

    def _find_identity(
        self,
        organization_id: UUID,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
    ) -> CustomerIdentityRead | None:
        query = (
            self.client.table("customer_identities")
            .select("*")
            .eq("organization_id", str(organization_id))
            .eq("provider", provider.lower())
        )
        if provider_user_id is not None:
            query = query.eq("provider_user_id", provider_user_id)
        if provider_username is not None:
            query = query.eq("provider_username", provider_username)
        if provider_phone is not None:
            query = query.eq("provider_phone", provider_phone)
        response = query.limit(1).execute()
        rows = response.data or []
        return CustomerIdentityRead.model_validate(rows[0]) if rows else None

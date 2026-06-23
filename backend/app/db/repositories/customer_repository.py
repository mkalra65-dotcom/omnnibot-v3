from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import LeadStage, PaginationOptions, RepositoryPage
from app.db.models.queries import CustomerFilters, SortOptions
from app.db.models.records import (
    CustomerCreate,
    CustomerIdentityCreate,
    CustomerIdentityRead,
    CustomerIdentityUpdate,
    CustomerRead,
    CustomerUpdate,
)
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class CustomerRepository(BaseRepository[CustomerRead, CustomerCreate, CustomerUpdate, CustomerFilters]):
    table_name = "customers"
    read_model = CustomerRead
    sortable_fields = {
        "created_at",
        "updated_at",
        "lead_score",
        "lead_stage",
        "lifetime_value_amount",
        "last_engaged_at",
        "display_name",
    }
    sort_aliases = {"lifetime_value": "lifetime_value_amount"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_by_organization(
        self,
        organization_id: UUID | OrganizationContext,
        filters: CustomerFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def list_by_lead_stage(
        self,
        organization_id: UUID | OrganizationContext,
        lead_stage: LeadStage,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        return self.list(
            organization_id,
            filters=CustomerFilters(lead_stage=lead_stage),
            pagination=pagination,
            sort=sort,
        )

    def find_by_email(
        self,
        organization_id: UUID | OrganizationContext,
        email: str,
    ) -> CustomerRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def update_lead_score(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        lead_score: float,
    ) -> CustomerRead | None:
        return self.update(organization_id, customer_id, {"lead_score": lead_score})

    def update_lead_stage(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        lead_stage: LeadStage,
    ) -> CustomerRead | None:
        return self.update(organization_id, customer_id, {"lead_stage": lead_stage})

    def create_identity(
        self,
        organization_id: UUID | OrganizationContext,
        payload: CustomerIdentityCreate | dict[str, Any] | BaseModel,
    ) -> CustomerIdentityRead:
        organization_uuid = self._organization_id(organization_id)
        data = self._dump_payload(payload)
        data["organization_id"] = str(organization_uuid)
        data["provider"] = str(data["provider"]).lower()
        response = self.client.table("customer_identities").insert(data).execute()
        row = self._first_row(response.data)
        if not row:
            raise LookupError("customer_identities mutation returned no row")
        return CustomerIdentityRead.model_validate(row)

    def update_identity(
        self,
        organization_id: UUID | OrganizationContext,
        identity_id: UUID,
        payload: CustomerIdentityUpdate | dict[str, Any] | BaseModel,
    ) -> CustomerIdentityRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_identity_by_id(organization_id, identity_id)
        response = (
            self.client.table("customer_identities")
            .update(data)
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(identity_id))
            .execute()
        )
        row = self._first_row(response.data)
        return CustomerIdentityRead.model_validate(row) if row else None

    def get_identity_by_id(
        self,
        organization_id: UUID | OrganizationContext,
        identity_id: UUID,
    ) -> CustomerIdentityRead | None:
        response = (
            self.client.table("customer_identities")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(identity_id))
            .limit(1)
            .execute()
        )
        row = self._first_row(response.data)
        return CustomerIdentityRead.model_validate(row) if row else None

    def list_identities_for_customer(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
    ) -> list[CustomerIdentityRead]:
        response = (
            self.client.table("customer_identities")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("customer_id", str(customer_id))
            .order("created_at", desc=False)
            .execute()
        )
        return [CustomerIdentityRead.model_validate(row) for row in response.data or []]

    def find_identity(
        self,
        organization_id: UUID | OrganizationContext,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
    ) -> CustomerIdentityRead | None:
        if provider_user_id is None and provider_username is None and provider_phone is None:
            return None

        query = (
            self.client.table("customer_identities")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("provider", provider.lower())
        )
        if provider_user_id is not None:
            query = query.eq("provider_user_id", provider_user_id)
        if provider_username is not None:
            query = query.eq("provider_username", provider_username)
        if provider_phone is not None:
            query = query.eq("provider_phone", provider_phone)

        response = query.limit(1).execute()
        row = self._first_row(response.data)
        return CustomerIdentityRead.model_validate(row) if row else None

    def list_identities_by_provider_user_id(
        self,
        organization_id: UUID | OrganizationContext,
        provider: str,
        provider_user_id: str,
        limit: int = 2,
    ) -> list[CustomerIdentityRead]:
        response = (
            self.client.table("customer_identities")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("provider", provider.lower())
            .eq("provider_user_id", provider_user_id)
            .limit(limit)
            .execute()
        )
        return [CustomerIdentityRead.model_validate(row) for row in response.data or []]

    def find_or_create_identity(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CustomerIdentityRead:
        existing = self.find_identity(
            organization_id=organization_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_username=provider_username,
            provider_phone=provider_phone,
        )
        if existing is not None:
            return existing

        return self.create_identity(
            organization_id,
            {
                "customer_id": customer_id,
                "provider": provider,
                "provider_user_id": provider_user_id,
                "provider_username": provider_username,
                "provider_phone": provider_phone,
                "metadata": metadata or {},
            },
        )

    def find_by_identity(
        self,
        organization_id: UUID | OrganizationContext,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
    ) -> CustomerRead | None:
        identity = self.find_identity(
            organization_id=organization_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_username=provider_username,
            provider_phone=provider_phone,
        )
        if identity is None:
            return None
        return self.get_by_id(organization_id, identity.customer_id)

    def hard_delete_identity(
        self,
        organization_id: UUID | OrganizationContext,
        identity_id: UUID,
    ) -> bool:
        # Hard delete should not be exposed through services without explicit approval.
        response = (
            self.client.table("customer_identities")
            .delete()
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(identity_id))
            .execute()
        )
        return bool(response.data)

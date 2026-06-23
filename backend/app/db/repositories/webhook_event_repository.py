from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage
from app.db.models.queries import SortOptions, WebhookEventFilters
from app.db.models.records import WebhookEventCreate, WebhookEventRead, WebhookEventUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class WebhookEventRepository(
    BaseRepository[WebhookEventRead, WebhookEventCreate, WebhookEventUpdate, WebhookEventFilters]
):
    table_name = "webhook_events"
    read_model = WebhookEventRead
    sortable_fields = {"created_at", "received_at", "processed_at", "status", "event_type"}
    default_sort_field = "received_at"

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create(
        self,
        payload: WebhookEventCreate | dict[str, Any] | BaseModel,
    ) -> WebhookEventRead:
        data = self._dump_payload(payload)
        if "provider" in data:
            data["provider"] = str(data["provider"]).lower()
        response = self.client.table(self.table_name).insert(data).execute()
        return self._coerce_required(response.data)

    def update(
        self,
        event_id: UUID,
        payload: WebhookEventUpdate | dict[str, Any] | BaseModel,
    ) -> WebhookEventRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_by_id_unscoped(event_id)

        response = (
            self.client.table(self.table_name)
            .update(data)
            .eq("id", str(event_id))
            .execute()
        )
        return self._coerce_optional(response.data)

    def get_by_id_unscoped(self, event_id: UUID) -> WebhookEventRead | None:
        response = (
            self.client.table(self.table_name)
            .select("*")
            .eq("id", str(event_id))
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def list_by_organization(
        self,
        organization_id: UUID | OrganizationContext,
        filters: WebhookEventFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[WebhookEventRead]:
        query = self._scoped_select(organization_id)
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def list_unresolved(
        self,
        provider: str | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[WebhookEventRead]:
        query = self.client.table(self.table_name).select("*", count="exact").eq("resolved", False)
        if provider is not None:
            query = query.eq("provider", provider.lower())
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def get_by_delivery_id(
        self,
        provider: str,
        delivery_id: str,
    ) -> WebhookEventRead | None:
        return self._get_by_provider_key(provider, "delivery_id", delivery_id)

    def get_by_external_event_id(
        self,
        provider: str,
        external_event_id: str,
    ) -> WebhookEventRead | None:
        return self._get_by_provider_key(provider, "external_event_id", external_event_id)

    def _apply_filters(self, query, filters: WebhookEventFilters | None):
        query = super()._apply_filters(query, filters)
        if filters is None:
            return query

        if filters.provider is not None:
            query = query.eq("provider", filters.provider.lower())
        if filters.resolved is not None:
            query = query.eq("resolved", filters.resolved)
        if filters.phone_number_id is not None:
            query = query.eq("phone_number_id", filters.phone_number_id)

        return query

    def _get_by_provider_key(
        self,
        provider: str,
        key_field: str,
        key_value: str,
    ) -> WebhookEventRead | None:
        response = (
            self.client.table(self.table_name)
            .select("*")
            .eq("provider", provider.lower())
            .eq(key_field, key_value)
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

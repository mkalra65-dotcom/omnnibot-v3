from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import OrganizationFilters, SortOptions
from app.db.models.records import OrganizationCreate, OrganizationRead, OrganizationUpdate


class OrganizationRepository:
    table_name = "organizations"
    read_model = OrganizationRead
    sortable_fields = {"created_at", "updated_at", "name", "slug"}
    default_sort_field = "created_at"

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_by_id(self, organization_id: UUID) -> OrganizationRead | None:
        response = (
            self.client.table(self.table_name)
            .select("*")
            .eq("id", str(organization_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self.read_model.model_validate(rows[0]) if rows else None

    def exists(self, organization_id: UUID) -> bool:
        response = (
            self.client.table(self.table_name)
            .select("id")
            .eq("id", str(organization_id))
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def create(self, payload: OrganizationCreate | dict[str, Any]) -> OrganizationRead:
        data = self._dump_payload(payload)
        response = self.client.table(self.table_name).insert(data).execute()
        return self._first_model(response.data)

    def update(self, organization_id: UUID, payload: OrganizationUpdate | dict[str, Any]) -> OrganizationRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_by_id(organization_id)
        response = (
            self.client.table(self.table_name)
            .update(data)
            .eq("id", str(organization_id))
            .execute()
        )
        return self._first_model_or_none(response.data)

    def delete(self, organization_id: UUID) -> bool:
        response = (
            self.client.table(self.table_name)
            .delete()
            .eq("id", str(organization_id))
            .execute()
        )
        return bool(response.data)

    def list(
        self,
        filters: OrganizationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[OrganizationRead]:
        pagination = pagination or PaginationOptions()
        query = self.client.table(self.table_name).select("*", count="exact")
        query = self._apply_filters(query, filters)
        query = self._apply_sort(query, sort)
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count or len(rows))
        return RepositoryPage(
            items=[self.read_model.model_validate(row) for row in rows],
            total=total,
            page=pagination.page or ((offset // max(limit, 1)) + 1),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def _apply_filters(self, query, filters: OrganizationFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.eq("status", filters.status.value if isinstance(filters.status, Enum) else filters.status)
        for field_name in ("created_from", "updated_from"):
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.gte(field_name.replace("_from", "_at"), self._serialize_datetime(value))
        for field_name in ("created_to", "updated_to"):
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.lte(field_name.replace("_to", "_at"), self._serialize_datetime(value))
        return query

    def _apply_sort(self, query, sort: SortOptions | None):
        sort = sort or SortOptions()
        sort_field = sort.field if sort.field in self.sortable_fields else self.default_sort_field
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _dump_payload(self, payload: OrganizationCreate | OrganizationUpdate | dict[str, Any]) -> dict[str, Any]:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json", exclude_unset=True, exclude_none=True)  # type: ignore[no-any-return]
        return {k: v for k, v in dict(payload).items() if v is not None}

    def _first_model(self, data: Any) -> OrganizationRead:
        row = self._first_row(data)
        return self.read_model.model_validate(row)

    def _first_model_or_none(self, data: Any) -> OrganizationRead | None:
        row = self._first_row(data)
        return self.read_model.model_validate(row) if row else None

    def _first_row(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            return data
        return {}

    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

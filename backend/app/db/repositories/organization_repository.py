from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import OrganizationFilters, SortOptions
from app.db.models.records import OrganizationCreate, OrganizationRead, OrganizationUpdate


class OrganizationRepository:
    table_name = "organizations"
    read_model = OrganizationRead
    sortable_fields = {"created_at", "updated_at", "name", "slug", "status"}
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
        return self._coerce_optional(response.data)

    def get_by_slug(self, slug: str) -> OrganizationRead | None:
        response = (
            self.client.table(self.table_name)
            .select("*")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

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
        total = int(response.count if response.count is not None else len(rows))
        return RepositoryPage(
            items=[self.read_model.model_validate(row) for row in rows],
            total=total,
            page=pagination.page or ((offset // max(limit, 1)) + 1),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def create(self, payload: OrganizationCreate | dict[str, Any] | BaseModel) -> OrganizationRead:
        response = self.client.table(self.table_name).insert(self._dump_payload(payload)).execute()
        return self._coerce_required(response.data)

    def update(
        self,
        organization_id: UUID,
        payload: OrganizationUpdate | dict[str, Any] | BaseModel,
    ) -> OrganizationRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_by_id(organization_id)
        response = (
            self.client.table(self.table_name)
            .update(data)
            .eq("id", str(organization_id))
            .execute()
        )
        return self._coerce_optional(response.data)

    def exists(self, organization_id: UUID) -> bool:
        response = (
            self.client.table(self.table_name)
            .select("id")
            .eq("id", str(organization_id))
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def hard_delete(self, organization_id: UUID) -> bool:
        # Hard delete should not be exposed through services without explicit approval.
        response = (
            self.client.table(self.table_name)
            .delete()
            .eq("id", str(organization_id))
            .execute()
        )
        return bool(response.data)

    def _apply_filters(self, query, filters: OrganizationFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.eq("status", self._serialize(filters.status))
        for attr_name, column_name, operator in (
            ("created_from", "created_at", "gte"),
            ("created_to", "created_at", "lte"),
            ("updated_from", "updated_at", "gte"),
            ("updated_to", "updated_at", "lte"),
        ):
            value = getattr(filters, attr_name, None)
            if value is not None:
                query = getattr(query, operator)(column_name, self._serialize(value))
        return query

    def _apply_sort(self, query, sort: SortOptions | None):
        sort = sort or SortOptions(field=self.default_sort_field)
        sort_field = sort.field if sort.field in self.sortable_fields else self.default_sort_field
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _coerce_required(self, data: Any) -> OrganizationRead:
        row = self._first_row(data)
        if not row:
            raise LookupError("organizations mutation returned no row")
        return self.read_model.model_validate(row)

    def _coerce_optional(self, data: Any) -> OrganizationRead | None:
        row = self._first_row(data)
        return self.read_model.model_validate(row) if row else None

    def _first_row(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            return data
        return {}

    def _dump_payload(self, payload: OrganizationCreate | OrganizationUpdate | dict[str, Any] | BaseModel) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw = payload.model_dump(mode="python", exclude_unset=True, exclude_none=True)
        else:
            raw = {key: value for key, value in dict(payload).items() if value is not None}
        return {key: self._serialize(value) for key, value in raw.items()}

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        return value

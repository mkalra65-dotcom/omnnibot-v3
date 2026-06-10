from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import BaseListFilters, SortOptions
from app.db.models.records import BaseReadModel

TRead = TypeVar("TRead", bound=BaseReadModel)
TCreate = TypeVar("TCreate")
TUpdate = TypeVar("TUpdate")
TFilters = TypeVar("TFilters", bound=BaseListFilters)


@dataclass(frozen=True, slots=True)
class OrganizationContext:
    organization_id: UUID
    user_id: UUID | None = None
    membership_id: UUID | None = None
    role: str | None = None
    request_id: str | None = None


TenantContext = OrganizationContext


class BaseRepository(Generic[TRead, TCreate, TUpdate, TFilters]):
    table_name: ClassVar[str]
    read_model: ClassVar[type[TRead]]
    default_sort_field: ClassVar[str] = "created_at"
    sortable_fields: ClassVar[set[str]] = {"created_at", "updated_at"}
    sort_aliases: ClassVar[dict[str, str]] = {}

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_by_id(
        self,
        organization_id: UUID | OrganizationContext,
        record_id: UUID,
    ) -> TRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("id", str(record_id))
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def list(
        self,
        organization_id: UUID | OrganizationContext,
        filters: TFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[TRead]:
        query = self._scoped_select(organization_id)
        query = self._apply_filters(query, filters)
        query = self._apply_sort(query, sort)
        return self._page(query, pagination)

    def create(
        self,
        organization_id: UUID | OrganizationContext,
        payload: TCreate | dict[str, Any] | BaseModel,
    ) -> TRead:
        organization_uuid = self._organization_id(organization_id)
        data = self._dump_payload(payload)
        data["organization_id"] = str(organization_uuid)
        response = self.client.table(self.table_name).insert(data).execute()
        return self._coerce_required(response.data)

    def update(
        self,
        organization_id: UUID | OrganizationContext,
        record_id: UUID,
        payload: TUpdate | dict[str, Any] | BaseModel,
    ) -> TRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_by_id(organization_id, record_id)

        response = (
            self.client.table(self.table_name)
            .update(data)
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(record_id))
            .execute()
        )
        return self._coerce_optional(response.data)

    def hard_delete(
        self,
        organization_id: UUID | OrganizationContext,
        record_id: UUID,
    ) -> bool:
        # Hard delete should not be exposed through services without explicit approval.
        response = (
            self.client.table(self.table_name)
            .delete()
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(record_id))
            .execute()
        )
        return bool(response.data)

    def exists(
        self,
        organization_id: UUID | OrganizationContext,
        record_id: UUID,
    ) -> bool:
        response = (
            self.client.table(self.table_name)
            .select("id")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(record_id))
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def _scoped_select(self, organization_id: UUID | OrganizationContext):
        return (
            self.client.table(self.table_name)
            .select("*", count="exact")
            .eq("organization_id", str(self._organization_id(organization_id)))
        )

    def _list_with_query(
        self,
        query,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[TRead]:
        query = self._apply_sort(query, sort)
        return self._page(query, pagination)

    def _page(self, query, pagination: PaginationOptions | None = None) -> RepositoryPage[TRead]:
        pagination = pagination or PaginationOptions()
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count if response.count is not None else len(rows))
        return RepositoryPage(
            items=[self._coerce_row(row) for row in rows],
            total=total,
            page=pagination.page or self._page_from_offset(offset, limit),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def _apply_filters(self, query, filters: TFilters | None):
        if filters is None:
            return query

        equality_fields = (
            "status",
            "lead_stage",
            "channel",
            "direction",
            "sender_type",
            "event_type",
            "category",
            "handoff_status",
            "assigned_membership_id",
        )
        for field_name in equality_fields:
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.eq(field_name, self._serialize(value))

        range_fields = (
            ("created_from", "created_at", "gte"),
            ("created_to", "created_at", "lte"),
            ("updated_from", "updated_at", "gte"),
            ("updated_to", "updated_at", "lte"),
        )
        for attr_name, column_name, operator in range_fields:
            value = getattr(filters, attr_name, None)
            if value is None:
                continue
            query = getattr(query, operator)(column_name, self._serialize(value))

        numeric_ranges = (
            ("min_lead_score", "lead_score", "gte"),
            ("max_lead_score", "lead_score", "lte"),
            ("min_lifetime_value", "lifetime_value_amount", "gte"),
            ("max_lifetime_value", "lifetime_value_amount", "lte"),
        )
        for attr_name, column_name, operator in numeric_ranges:
            value = getattr(filters, attr_name, None)
            if value is None:
                continue
            query = getattr(query, operator)(column_name, self._serialize(value))

        return query

    def _apply_sort(self, query, sort: SortOptions | None):
        sort = sort or SortOptions(field=self.default_sort_field)
        sort_field = self.sort_aliases.get(sort.field, sort.field)
        if sort_field not in self.sortable_fields:
            sort_field = self.default_sort_field
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _coerce_required(self, data: Any) -> TRead:
        row = self._first_row(data)
        if not row:
            raise LookupError(f"{self.table_name} mutation returned no row")
        return self._coerce_row(row)

    def _coerce_optional(self, data: Any) -> TRead | None:
        row = self._first_row(data)
        return self._coerce_row(row) if row else None

    def _coerce_row(self, row: dict[str, Any]) -> TRead:
        return self.read_model.model_validate(row)

    def _first_row(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            return data
        return {}

    def _dump_payload(self, payload: TCreate | TUpdate | dict[str, Any] | BaseModel) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, BaseModel):
            raw = payload.model_dump(mode="python", exclude_unset=True, exclude_none=True)
        elif is_dataclass(payload):
            raw = {key: value for key, value in asdict(payload).items() if value is not None}
        else:
            raw = {key: value for key, value in dict(payload).items() if value is not None}
        return {key: self._serialize(value) for key, value in raw.items()}

    def _organization_id(self, value: UUID | OrganizationContext) -> UUID:
        if isinstance(value, OrganizationContext):
            return value.organization_id
        return value

    def _page_from_offset(self, offset: int, limit: int) -> int:
        return (offset // max(limit, 1)) + 1

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        return value

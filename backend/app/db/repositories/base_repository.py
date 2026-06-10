from __future__ import annotations

from abc import ABC
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
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


class BaseRepository(ABC, Generic[TRead, TCreate, TUpdate, TFilters]):
    table_name: ClassVar[str]
    read_model: ClassVar[type[TRead]]
    default_sort_field: ClassVar[str] = "created_at"
    sortable_fields: ClassVar[set[str]] = {"created_at", "updated_at"}
    sort_aliases: ClassVar[dict[str, str]] = {}
    soft_delete_column: ClassVar[str | None] = None

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_by_id(
        self,
        organization_id: UUID,
        record_id: UUID,
        include_deleted: bool = False,
    ) -> TRead | None:
        response = (
            self._scoped_select(organization_id, include_deleted)
            .eq("id", str(record_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self._coerce_one(rows[0]) if rows else None

    def list(
        self,
        organization_id: UUID,
        filters: TFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
        include_deleted: bool = False,
    ) -> RepositoryPage[TRead]:
        pagination = pagination or PaginationOptions()
        query = self._scoped_select(organization_id, include_deleted)
        query = self._apply_filters(query, filters)
        query = self._apply_sort(query, sort)
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count or len(rows))
        return RepositoryPage(
            items=[self._coerce_one(row) for row in rows],
            total=total,
            page=pagination.page or self._page_from_offset(offset, limit),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def create(
        self,
        organization_id: UUID,
        payload: TCreate | dict[str, Any] | BaseModel,
    ) -> TRead:
        data = self._dump_payload(payload)
        data["organization_id"] = str(organization_id)
        response = self.client.table(self.table_name).insert(data).execute()
        row = self._first_row(response.data)
        return self._coerce_one(row)

    def update(
        self,
        organization_id: UUID,
        record_id: UUID,
        payload: TUpdate | dict[str, Any] | BaseModel,
        include_deleted: bool = False,
    ) -> TRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_by_id(organization_id, record_id, include_deleted=include_deleted)
        response = (
            self._scoped_query(organization_id, include_deleted)
            .eq("id", str(record_id))
            .update(data)
            .execute()
        )
        row = self._first_row(response.data)
        return self._coerce_one(row) if row else None

    def delete(
        self,
        organization_id: UUID,
        record_id: UUID,
        soft_delete: bool = False,
    ) -> bool:
        query = self._scoped_query(organization_id, include_deleted=True).eq("id", str(record_id))
        if soft_delete and self.soft_delete_column:
            payload = {self.soft_delete_column: datetime.now(timezone.utc).isoformat()}
            response = query.update(payload).execute()
            return bool(response.data)
        response = query.delete().execute()
        return bool(response.data)

    def exists(
        self,
        organization_id: UUID,
        record_id: UUID,
        include_deleted: bool = False,
    ) -> bool:
        response = (
            self._scoped_select(organization_id, include_deleted)
            .select("id")
            .eq("id", str(record_id))
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def _scoped_query(self, organization_id: UUID, include_deleted: bool = False):
        query = self.client.table(self.table_name).eq("organization_id", str(organization_id))
        if self.soft_delete_column and not include_deleted:
            query = query.is_(self.soft_delete_column, "null")
        return query

    def _scoped_select(self, organization_id: UUID, include_deleted: bool = False):
        return self._scoped_query(organization_id, include_deleted).select("*", count="exact")

    def _apply_filters(self, query, filters: TFilters | None):
        if filters is None:
            return query

        for field_name in ("status", "lead_stage", "channel", "direction", "sender_type", "event_type", "category"):
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.eq(field_name, self._scalar(value))

        for field_name in ("created_from", "updated_from"):
            value = getattr(filters, field_name, None)
            if value is not None:
                column = field_name.replace("_from", "_at")
                query = query.gte(column, self._serialize_datetime(value))

        for field_name in ("created_to", "updated_to"):
            value = getattr(filters, field_name, None)
            if value is not None:
                column = field_name.replace("_to", "_at")
                query = query.lte(column, self._serialize_datetime(value))

        if getattr(filters, "assigned_membership_id", None) is not None:
            query = query.eq("assigned_membership_id", str(filters.assigned_membership_id))

        if getattr(filters, "min_lead_score", None) is not None:
            query = query.gte("lead_score", filters.min_lead_score)
        if getattr(filters, "max_lead_score", None) is not None:
            query = query.lte("lead_score", filters.max_lead_score)
        if getattr(filters, "min_lifetime_value", None) is not None:
            query = query.gte("lifetime_value_amount", filters.min_lifetime_value)
        if getattr(filters, "max_lifetime_value", None) is not None:
            query = query.lte("lifetime_value_amount", filters.max_lifetime_value)

        return query

    def _apply_sort(self, query, sort: SortOptions | None):
        sort = sort or SortOptions()
        sort_field = self.sort_aliases.get(sort.field, sort.field)
        if sort_field not in self.sortable_fields:
            sort_field = self.default_sort_field
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _coerce_one(self, row: dict[str, Any]) -> TRead:
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
            return payload.model_dump(mode="json", exclude_unset=True, exclude_none=True)
        if is_dataclass(payload):
            return {k: self._scalar(v) for k, v in asdict(payload).items() if v is not None}
        return {k: self._scalar(v) for k, v in dict(payload).items() if v is not None}

    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

    def _page_from_offset(self, offset: int, limit: int) -> int:
        return (offset // max(limit, 1)) + 1

    def _scalar(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return value

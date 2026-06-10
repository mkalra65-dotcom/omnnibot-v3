from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage
from app.db.models.queries import LeadEventFilters, SortOptions
from app.db.models.records import LeadEventCreate, LeadEventRead
from app.db.repositories.base_repository import BaseRepository


class LeadEventRepository(BaseRepository[LeadEventRead, LeadEventCreate, LeadEventCreate, LeadEventFilters]):
    table_name = "lead_events"
    read_model = LeadEventRead
    sortable_fields = {"created_at"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create(self, organization_id: UUID, payload: LeadEventCreate | dict[str, Any]) -> LeadEventRead:
        return super().create(organization_id, payload)

    def list_by_customer(
        self,
        organization_id: UUID,
        customer_id: UUID,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        return self._list_scoped(organization_id, {"customer_id": str(customer_id)}, pagination, sort)

    def list_by_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        return self._list_scoped(organization_id, {"conversation_id": str(conversation_id)}, pagination, sort)

    def list_by_event_type(
        self,
        organization_id: UUID,
        event_type: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        return self._list_scoped(organization_id, {"event_type": event_type}, pagination, sort)

    def _list_scoped(
        self,
        organization_id: UUID,
        filters: dict[str, Any],
        pagination: PaginationOptions | None,
        sort: SortOptions | None,
    ) -> RepositoryPage[LeadEventRead]:
        pagination = pagination or PaginationOptions()
        query = self._scoped_select(organization_id)
        for key, value in filters.items():
            query = query.eq(key, value)
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

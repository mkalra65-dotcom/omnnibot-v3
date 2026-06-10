from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.db.models.common import LeadStage, PaginationOptions, RepositoryPage
from app.db.models.queries import LeadEventFilters, SortOptions
from app.db.models.records import LeadEventCreate, LeadEventRead
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class LeadEventRepository(BaseRepository[LeadEventRead, LeadEventCreate, LeadEventCreate, LeadEventFilters]):
    table_name = "lead_events"
    read_model = LeadEventRead
    sortable_fields = {"created_at"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_by_customer(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        filters: LeadEventFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        query = self._scoped_select(organization_id).eq("customer_id", str(customer_id))
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def list_by_conversation(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        filters: LeadEventFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        query = self._scoped_select(organization_id).eq("conversation_id", str(conversation_id))
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def list_by_stage(
        self,
        organization_id: UUID | OrganizationContext,
        lead_stage: LeadStage,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        return self.list(
            organization_id,
            filters=LeadEventFilters(lead_stage=lead_stage),
            pagination=pagination,
            sort=sort,
        )

    def list_by_event_type(
        self,
        organization_id: UUID | OrganizationContext,
        event_type: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[LeadEventRead]:
        return self.list(
            organization_id,
            filters=LeadEventFilters(event_type=event_type),
            pagination=pagination,
            sort=sort,
        )

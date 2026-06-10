from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import ChannelType, PaginationOptions, RepositoryPage
from app.db.models.queries import ConversationFilters, SortOptions
from app.db.models.records import ConversationCreate, ConversationRead, ConversationUpdate
from app.db.repositories.base_repository import BaseRepository


class ConversationRepository(
    BaseRepository[ConversationRead, ConversationCreate, ConversationUpdate, ConversationFilters]
):
    table_name = "conversations"
    read_model = ConversationRead
    sortable_fields = {"created_at", "updated_at", "last_message_at", "last_ai_response_at", "last_customer_response_at"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def get_by_id(self, organization_id: UUID, record_id: UUID, include_deleted: bool = False) -> ConversationRead | None:
        return super().get_by_id(organization_id, record_id, include_deleted=include_deleted)

    def create(self, organization_id: UUID, payload: ConversationCreate | dict[str, Any]) -> ConversationRead:
        return super().create(organization_id, payload)

    def update(
        self,
        organization_id: UUID,
        record_id: UUID,
        payload: ConversationUpdate | dict[str, Any],
        include_deleted: bool = False,
    ) -> ConversationRead | None:
        return super().update(organization_id, record_id, payload, include_deleted=include_deleted)

    def list_by_organization(
        self,
        organization_id: UUID,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def list_by_customer(
        self,
        organization_id: UUID,
        customer_id: UUID,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        filters = ConversationFilters()
        query = self._scoped_select(organization_id).eq("customer_id", str(customer_id))
        query = self._apply_filters(query, filters)
        query = self._apply_sort(query, sort)
        pagination = pagination or PaginationOptions()
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

    def find_open_conversation(
        self,
        organization_id: UUID,
        customer_id: UUID,
        channel: ChannelType | None = None,
    ) -> ConversationRead | None:
        query = (
            self._scoped_select(organization_id)
            .eq("customer_id", str(customer_id))
            .eq("status", "open")
        )
        if channel is not None:
            query = query.eq("channel", channel.value if hasattr(channel, "value") else channel)
        response = query.order("updated_at", desc=True).limit(1).execute()
        rows = response.data or []
        return self.read_model.model_validate(rows[0]) if rows else None

    def update_last_message(
        self,
        organization_id: UUID,
        record_id: UUID,
        last_message_id: UUID | None,
        last_message_at: datetime | None,
    ) -> ConversationRead | None:
        return self.update(
            organization_id,
            record_id,
            {
                "last_message_id": last_message_id,
                "last_message_at": last_message_at,
            },
        )

    def update_handoff_status(
        self,
        organization_id: UUID,
        record_id: UUID,
        handoff_status: str,
    ) -> ConversationRead | None:
        return self.update(organization_id, record_id, {"handoff_status": handoff_status})

    def update_followup_timestamps(
        self,
        organization_id: UUID,
        record_id: UUID,
        last_ai_response_at: datetime | None = None,
        last_customer_response_at: datetime | None = None,
    ) -> ConversationRead | None:
        payload: dict[str, Any] = {}
        if last_ai_response_at is not None:
            payload["last_ai_response_at"] = last_ai_response_at
        if last_customer_response_at is not None:
            payload["last_customer_response_at"] = last_customer_response_at
        if not payload:
            return self.get_by_id(organization_id, record_id)
        return self.update(organization_id, record_id, payload)

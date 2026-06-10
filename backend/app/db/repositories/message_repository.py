from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import ChannelType, PaginationOptions, RepositoryPage
from app.db.models.queries import MessageFilters, SortOptions
from app.db.models.records import MessageCreate, MessageRead, MessageUpdate
from app.db.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository[MessageRead, MessageCreate, MessageUpdate, MessageFilters]):
    table_name = "messages"
    read_model = MessageRead
    sortable_fields = {"created_at", "updated_at", "sent_at", "delivered_at", "read_at", "failed_at"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create(self, organization_id: UUID, payload: MessageCreate | dict[str, Any]) -> MessageRead:
        return super().create(organization_id, payload)

    def get_by_external_message_id(
        self,
        organization_id: UUID,
        external_message_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("external_message_id", organization_id, external_message_id, channel)

    def get_by_external_event_id(
        self,
        organization_id: UUID,
        external_event_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("external_event_id", organization_id, external_event_id, channel)

    def get_by_webhook_delivery_id(
        self,
        organization_id: UUID,
        webhook_delivery_id: str,
        channel: ChannelType | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("webhook_delivery_id", organization_id, webhook_delivery_id, channel)

    def list_by_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        filters: MessageFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[MessageRead]:
        pagination = pagination or PaginationOptions()
        query = self._scoped_select(organization_id).eq("conversation_id", str(conversation_id))
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

    def _get_by_external_key(
        self,
        key_field: str,
        organization_id: UUID,
        key_value: str,
        channel: ChannelType | None = None,
    ) -> MessageRead | None:
        query = self._scoped_select(organization_id).eq(key_field, key_value)
        if channel is not None:
            query = query.eq("channel", channel.value)
        response = query.limit(1).execute()
        rows = response.data or []
        return self.read_model.model_validate(rows[0]) if rows else None

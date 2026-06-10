from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.db.models.common import ChannelType, PaginationOptions, RepositoryPage
from app.db.models.queries import MessageFilters, SortOptions
from app.db.models.records import MessageCreate, MessageRead, MessageUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class MessageRepository(BaseRepository[MessageRead, MessageCreate, MessageUpdate, MessageFilters]):
    table_name = "messages"
    read_model = MessageRead
    sortable_fields = {
        "created_at",
        "external_created_at",
        "sent_at",
        "delivered_at",
        "read_at",
        "failed_at",
    }

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_by_conversation(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        filters: MessageFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[MessageRead]:
        query = self._scoped_select(organization_id).eq("conversation_id", str(conversation_id))
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def list_by_customer(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        filters: MessageFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[MessageRead]:
        query = self._scoped_select(organization_id).eq("customer_id", str(customer_id))
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def get_by_external_message_id(
        self,
        organization_id: UUID | OrganizationContext,
        external_message_id: str,
        channel: ChannelType | str | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("external_message_id", organization_id, external_message_id, channel)

    def get_by_external_event_id(
        self,
        organization_id: UUID | OrganizationContext,
        external_event_id: str,
        channel: ChannelType | str | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("external_event_id", organization_id, external_event_id, channel)

    def get_by_webhook_delivery_id(
        self,
        organization_id: UUID | OrganizationContext,
        webhook_delivery_id: str,
        channel: ChannelType | str | None = None,
    ) -> MessageRead | None:
        return self._get_by_external_key("webhook_delivery_id", organization_id, webhook_delivery_id, channel)

    def _get_by_external_key(
        self,
        key_field: str,
        organization_id: UUID | OrganizationContext,
        key_value: str,
        channel: ChannelType | str | None = None,
    ) -> MessageRead | None:
        query = self._scoped_select(organization_id).eq(key_field, key_value)
        if channel is not None:
            query = query.eq("channel", self._serialize(channel))
        response = query.limit(1).execute()
        return self._coerce_optional(response.data)

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import ChannelType, ConversationStatus, PaginationOptions, RepositoryPage
from app.db.models.queries import ConversationFilters, SortOptions
from app.db.models.records import ConversationCreate, ConversationRead, ConversationUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class ConversationRepository(
    BaseRepository[ConversationRead, ConversationCreate, ConversationUpdate, ConversationFilters]
):
    table_name = "conversations"
    read_model = ConversationRead
    sortable_fields = {
        "created_at",
        "updated_at",
        "last_message_at",
        "last_ai_response_at",
        "last_customer_response_at",
        "opened_at",
        "closed_at",
        "priority",
    }

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_by_organization(
        self,
        organization_id: UUID | OrganizationContext,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def list_by_customer(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ConversationRead]:
        query = self._scoped_select(organization_id).eq("customer_id", str(customer_id))
        query = self._apply_filters(query, filters)
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def find_by_external_conversation_id(
        self,
        organization_id: UUID | OrganizationContext,
        channel: ChannelType | str,
        external_conversation_id: str,
    ) -> ConversationRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("channel", self._serialize(channel))
            .eq("external_conversation_id", external_conversation_id)
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def find_latest_open_for_customer(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        channel: ChannelType | str | None = None,
    ) -> ConversationRead | None:
        query = (
            self._scoped_select(organization_id)
            .eq("customer_id", str(customer_id))
            .eq("status", ConversationStatus.OPEN.value)
        )
        if channel is not None:
            query = query.eq("channel", self._serialize(channel))
        response = query.order("updated_at", desc=True).limit(1).execute()
        return self._coerce_optional(response.data)

    def find_open_conversation(
        self,
        organization_id: UUID | OrganizationContext,
        customer_id: UUID,
        channel: ChannelType | str | None = None,
    ) -> ConversationRead | None:
        return self.find_latest_open_for_customer(
            organization_id=organization_id,
            customer_id=customer_id,
            channel=channel,
        )

    def update_last_message(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        last_message_id: UUID | None,
        last_message_at: datetime | None,
    ) -> ConversationRead | None:
        return self.update(
            organization_id,
            conversation_id,
            {
                "last_message_id": last_message_id,
                "last_message_at": last_message_at,
            },
        )

    def update_handoff_status(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        handoff_status: str,
    ) -> ConversationRead | None:
        return self.update(organization_id, conversation_id, {"handoff_status": handoff_status})

    def update_followup_timestamps(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        payload: ConversationUpdate | dict[str, Any] | BaseModel,
    ) -> ConversationRead | None:
        data = self._dump_payload(payload)
        allowed = {"last_ai_response_at", "last_customer_response_at"}
        return self.update(
            organization_id,
            conversation_id,
            {key: value for key, value in data.items() if key in allowed},
        )

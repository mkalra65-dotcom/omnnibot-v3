from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, WhatsAppAccountStatus
from app.db.models.queries import SortOptions, WhatsAppAccountFilters
from app.db.models.records import WhatsAppAccountCreate, WhatsAppAccountRead, WhatsAppAccountUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class WhatsAppAccountRepository(
    BaseRepository[WhatsAppAccountRead, WhatsAppAccountCreate, WhatsAppAccountUpdate, WhatsAppAccountFilters]
):
    table_name = "whatsapp_accounts"
    read_model = WhatsAppAccountRead
    sortable_fields = {"created_at", "updated_at", "status", "phone_number_id"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_by_organization(
        self,
        organization_id: UUID | OrganizationContext,
        filters: WhatsAppAccountFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[WhatsAppAccountRead]:
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def get_by_phone_number_id(
        self,
        organization_id: UUID | OrganizationContext,
        phone_number_id: str,
        status: WhatsAppAccountStatus | str | None = None,
    ) -> WhatsAppAccountRead | None:
        query = self._scoped_select(organization_id).eq("phone_number_id", phone_number_id)
        if status is not None:
            query = query.eq("status", self._serialize(status))
        response = query.limit(1).execute()
        return self._coerce_optional(response.data)

    def list_active_by_phone_number_id(
        self,
        phone_number_id: str,
        limit: int = 2,
    ) -> list[WhatsAppAccountRead]:
        response = (
            self.client.table(self.table_name)
            .select("*")
            .eq("phone_number_id", phone_number_id)
            .eq("status", WhatsAppAccountStatus.ACTIVE.value)
            .limit(limit)
            .execute()
        )
        rows = response.data or []
        return [self._coerce_row(row) for row in rows]

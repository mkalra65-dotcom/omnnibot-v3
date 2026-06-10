from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import FaqStatus, PaginationOptions, RepositoryPage
from app.db.models.queries import FaqFilters, SortOptions
from app.db.models.records import FaqCreate, FaqRead, FaqUpdate
from app.db.repositories.base_repository import BaseRepository


class FaqRepository(BaseRepository[FaqRead, FaqCreate, FaqUpdate, FaqFilters]):
    table_name = "faq_entries"
    read_model = FaqRead
    sortable_fields = {"created_at", "updated_at", "usage_count", "last_used_at", "question", "normalized_question"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create(self, organization_id: UUID, payload: FaqCreate | dict[str, Any]) -> FaqRead:
        return super().create(organization_id, payload)

    def update(
        self,
        organization_id: UUID,
        record_id: UUID,
        payload: FaqUpdate | dict[str, Any],
        include_deleted: bool = False,
    ) -> FaqRead | None:
        return super().update(organization_id, record_id, payload, include_deleted=include_deleted)

    def list_active(
        self,
        organization_id: UUID,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[FaqRead]:
        filters = FaqFilters(status=FaqStatus.ACTIVE)
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def find_by_normalized_question(self, organization_id: UUID, normalized_question: str) -> FaqRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("normalized_question", self._normalize_text(normalized_question))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self.read_model.model_validate(rows[0]) if rows else None

    def increment_usage_count(self, organization_id: UUID, record_id: UUID, increment: int = 1) -> FaqRead | None:
        current = self.get_by_id(organization_id, record_id)
        if current is None:
            return None
        updated_count = current.usage_count + increment
        return self.update(organization_id, record_id, {"usage_count": updated_count})

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

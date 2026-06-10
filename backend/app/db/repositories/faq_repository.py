from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.db.models.common import FaqStatus, PaginationOptions, RepositoryPage
from app.db.models.queries import FaqFilters, SortOptions
from app.db.models.records import FaqCreate, FaqRead, FaqUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class FaqRepository(BaseRepository[FaqRead, FaqCreate, FaqUpdate, FaqFilters]):
    table_name = "faq_entries"
    read_model = FaqRead
    sortable_fields = {
        "created_at",
        "updated_at",
        "question",
        "normalized_question",
        "usage_count",
        "last_used_at",
    }

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_active(
        self,
        organization_id: UUID | OrganizationContext,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[FaqRead]:
        return self.list(
            organization_id,
            filters=FaqFilters(status=FaqStatus.ACTIVE),
            pagination=pagination,
            sort=sort,
        )

    def list_by_category(
        self,
        organization_id: UUID | OrganizationContext,
        category: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[FaqRead]:
        return self.list(
            organization_id,
            filters=FaqFilters(category=category),
            pagination=pagination,
            sort=sort,
        )

    def find_by_normalized_question(
        self,
        organization_id: UUID | OrganizationContext,
        normalized_question: str,
    ) -> FaqRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("normalized_question", self._normalize_text(normalized_question))
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def search_by_question(
        self,
        organization_id: UUID | OrganizationContext,
        question_query: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[FaqRead]:
        query = self._scoped_select(organization_id).ilike("question", f"%{question_query.strip()}%")
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

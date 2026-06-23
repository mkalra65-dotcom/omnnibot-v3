from __future__ import annotations

from uuid import UUID

from app.db.models.common import PaginationOptions, RepositoryPage
from app.db.models.queries import AiDraftReviewFilters, SortOptions
from app.db.models.records import AiDraftReviewCreate, AiDraftReviewRead, AiDraftReviewUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


SENDABLE_REVIEW_STATUSES = ("approved", "edited")


class AiDraftReviewRepository(
    BaseRepository[AiDraftReviewRead, AiDraftReviewCreate, AiDraftReviewUpdate, AiDraftReviewFilters]
):
    table_name = "ai_draft_reviews"
    read_model = AiDraftReviewRead
    sortable_fields = {"created_at", "updated_at", "approved_at", "rejected_at"}

    def list_pending(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[AiDraftReviewRead]:
        filters = AiDraftReviewFilters(status="pending", conversation_id=conversation_id)
        return self.list(
            organization_id=organization_id,
            filters=filters,
            pagination=pagination,
            sort=sort,
        )

    def get_by_send_idempotency_key(
        self,
        organization_id: UUID | OrganizationContext,
        send_idempotency_key: str,
    ) -> AiDraftReviewRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("send_idempotency_key", send_idempotency_key)
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def claim_for_send(
        self,
        organization_id: UUID | OrganizationContext,
        review_id: UUID,
        send_idempotency_key: str,
    ) -> AiDraftReviewRead | None:
        response = (
            self.client.table(self.table_name)
            .update({"send_idempotency_key": send_idempotency_key})
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(review_id))
            .in_("status", list(SENDABLE_REVIEW_STATUSES))
            .is_("send_idempotency_key", "null")
            .execute()
        )
        return self._coerce_optional(response.data)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import PaginationOptions, RepositoryPage
from app.db.models.queries import SortOptions
from app.db.models.records import AiDraftReviewCreate, AiDraftReviewRead, AiDraftReviewUpdate
from app.db.repositories.ai_draft_review_repository import AiDraftReviewRepository
from app.db.repositories.base_repository import OrganizationContext
from app.services.ai_draft_response import AIDraftResponseDraft
from app.services.base import BaseService
from app.services.organization_access import OrganizationAccessService, TenantContext


AI_DRAFT_REVIEW_ACTION_ROLES = {"agent", "manager", "admin", "owner"}
AI_DRAFT_REVIEW_STATUSES = {
    "pending",
    "approved",
    "edited",
    "rejected",
    "ready_to_send",
    "sent",
}


class AIDraftReviewService(BaseService):
    def __init__(
        self,
        *,
        repository: AiDraftReviewRepository | Any | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
        organization_access_service: OrganizationAccessService | Any | None = None,
    ) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        self.repository = repository or AiDraftReviewRepository(self.supabase_factory.get_service_client())
        self.organization_access_service = organization_access_service or OrganizationAccessService(
            self.supabase_factory
        )

    def create_review_from_draft(
        self,
        *,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID,
        draft_text: str,
        customer_id: UUID | None = None,
        source_message_id: UUID | None = None,
        ai_interaction_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AiDraftReviewRead:
        self._require_non_blank(draft_text, "draft_text")
        context = self._context(organization_id)
        return self.repository.create(
            context,
            AiDraftReviewCreate(
                conversation_id=conversation_id,
                customer_id=customer_id,
                source_message_id=source_message_id,
                ai_interaction_id=ai_interaction_id,
                draft_text=draft_text,
                status="pending",
                metadata={
                    "content_trust": "ai_generated_untrusted_until_seller_approval",
                    **(metadata or {}),
                },
            ),
        )

    def store_draft(self, draft: AIDraftResponseDraft) -> AiDraftReviewRead:
        ai_interaction_id = draft.usage_metadata.get("ai_interaction_id")
        return self.create_review_from_draft(
            organization_id=draft.organization_id,
            conversation_id=draft.conversation_id,
            customer_id=draft.customer_id,
            ai_interaction_id=UUID(str(ai_interaction_id)) if ai_interaction_id else None,
            draft_text=draft.generated_response,
            metadata={
                "source": "ai_draft_response",
                "model": draft.model,
                "usage": draft.usage_metadata,
                **draft.metadata,
            },
        )

    def list_pending_reviews(
        self,
        organization_id: UUID | OrganizationContext,
        conversation_id: UUID | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[AiDraftReviewRead]:
        return self.repository.list_pending(
            self._context(organization_id),
            conversation_id=conversation_id,
            pagination=pagination,
            sort=sort,
        )

    def approve_review(self, tenant: TenantContext, review_id: UUID) -> AiDraftReviewRead:
        self._require_action_role(tenant)
        review = self._require_review(tenant.organization_id, review_id)
        self._require_pending(review)
        return self._update_required(
            tenant.organization_id,
            review_id,
            AiDraftReviewUpdate(
                status="approved",
                approved_by_membership_id=tenant.membership_id,
                approved_at=self._now(),
                metadata={
                    **review.metadata,
                    "seller_approved_content_source": "draft_text",
                    "customer_facing_side_effects": False,
                },
            ),
        )

    def edit_review(self, tenant: TenantContext, review_id: UUID, edited_text: str) -> AiDraftReviewRead:
        self._require_action_role(tenant)
        self._require_non_blank(edited_text, "edited_text")
        review = self._require_review(tenant.organization_id, review_id)
        self._require_pending(review)
        return self._update_required(
            tenant.organization_id,
            review_id,
            AiDraftReviewUpdate(
                edited_text=edited_text,
                status="edited",
                approved_by_membership_id=tenant.membership_id,
                approved_at=self._now(),
                metadata={
                    **review.metadata,
                    "seller_approved_content_source": "edited_text",
                    "customer_facing_side_effects": False,
                },
            ),
        )

    def reject_review(self, tenant: TenantContext, review_id: UUID) -> AiDraftReviewRead:
        self._require_action_role(tenant)
        review = self._require_review(tenant.organization_id, review_id)
        self._require_pending(review)
        return self._update_required(
            tenant.organization_id,
            review_id,
            AiDraftReviewUpdate(
                status="rejected",
                rejected_by_membership_id=tenant.membership_id,
                rejected_at=self._now(),
                metadata={
                    **review.metadata,
                    "seller_approved_content_source": None,
                    "customer_facing_side_effects": False,
                },
            ),
        )

    def _require_action_role(self, tenant: TenantContext) -> None:
        self.organization_access_service.require_role(
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            allowed_roles=AI_DRAFT_REVIEW_ACTION_ROLES,
        )

    def _require_review(self, organization_id: UUID, review_id: UUID) -> AiDraftReviewRead:
        review = self.repository.get_by_id(organization_id, review_id)
        if review is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI draft review not found",
            )
        return review

    def _require_pending(self, review: AiDraftReviewRead) -> None:
        if review.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="AI draft review is not pending",
            )

    def _update_required(
        self,
        organization_id: UUID,
        review_id: UUID,
        payload: AiDraftReviewUpdate,
    ) -> AiDraftReviewRead:
        review = self.repository.update(organization_id, review_id, payload)
        if review is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI draft review not found",
            )
        return review

    def _context(self, value: UUID | OrganizationContext) -> OrganizationContext:
        if isinstance(value, OrganizationContext):
            return value
        return OrganizationContext(organization_id=value)

    def _require_non_blank(self, value: str, field_name: str) -> None:
        if not value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must not be blank",
            )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

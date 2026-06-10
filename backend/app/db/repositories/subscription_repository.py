from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import SortOptions, SubscriptionFilters
from app.db.models.records import (
    OrganizationSubscriptionRead,
    SubscriptionPlanLimits,
    SubscriptionPlanRead,
)


class SubscriptionRepository:
    active_subscription_statuses = ("trialing", "active", "past_due")

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_active_subscription(self, organization_id: UUID) -> OrganizationSubscriptionRead | None:
        response = (
            self.client.table("organization_subscriptions")
            .select("*")
            .eq("organization_id", str(organization_id))
            .in_("status", list(self.active_subscription_statuses))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return OrganizationSubscriptionRead.model_validate(rows[0]) if rows else None

    def get_plan_limits(self, organization_id: UUID) -> SubscriptionPlanLimits | None:
        active_subscription = self.get_active_subscription(organization_id)
        if active_subscription is None:
            return None
        plan = self._get_plan_by_id(active_subscription.subscription_plan_id)
        if plan is None:
            return None
        return SubscriptionPlanLimits(
            subscription_plan_id=plan.id,
            subscription_plan_name=plan.name,
            subscription_plan_slug=plan.slug,
            monthly_message_limit=plan.monthly_message_limit,
            monthly_ai_request_limit=plan.monthly_ai_request_limit,
            monthly_token_limit=plan.monthly_token_limit,
        )

    def list_plans(
        self,
        filters: SubscriptionFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[SubscriptionPlanRead]:
        pagination = pagination or PaginationOptions()
        query = self.client.table("subscription_plans").select("*", count="exact")
        query = self._apply_filters(query, filters)
        query = self._apply_sort(query, sort)
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count or len(rows))
        return RepositoryPage(
            items=[SubscriptionPlanRead.model_validate(row) for row in rows],
            total=total,
            page=pagination.page or ((offset // max(limit, 1)) + 1),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def _get_plan_by_id(self, plan_id: UUID) -> SubscriptionPlanRead | None:
        response = (
            self.client.table("subscription_plans")
            .select("*")
            .eq("id", str(plan_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return SubscriptionPlanRead.model_validate(rows[0]) if rows else None

    def _apply_filters(self, query, filters: SubscriptionFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.eq("status", filters.status)
        if filters.plan_slug is not None:
            query = query.eq("slug", filters.plan_slug)
        for field_name in ("created_from", "updated_from"):
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.gte(field_name.replace("_from", "_at"), self._serialize_datetime(value))
        for field_name in ("created_to", "updated_to"):
            value = getattr(filters, field_name, None)
            if value is not None:
                query = query.lte(field_name.replace("_to", "_at"), self._serialize_datetime(value))
        return query

    def _apply_sort(self, query, sort: SortOptions | None):
        sort = sort or SortOptions()
        sort_field = sort.field if sort.field in {"created_at", "updated_at", "name", "slug"} else "created_at"
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

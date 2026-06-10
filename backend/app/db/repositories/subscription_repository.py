from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from supabase import Client

from app.db.models.common import PaginationOptions, RepositoryPage, SortDirection
from app.db.models.queries import SortOptions, SubscriptionFilters
from app.db.models.records import OrganizationSubscriptionRead, SubscriptionPlanLimits
from app.db.repositories.base_repository import OrganizationContext


class SubscriptionRepository:
    active_subscription_statuses = ("trialing", "active", "past_due")
    plan_sortable_fields = {"created_at", "updated_at", "name", "slug", "status"}
    subscription_sortable_fields = {"created_at", "updated_at", "current_period_start", "current_period_end", "status"}

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_active_subscription(
        self,
        organization_id: UUID | OrganizationContext,
    ) -> OrganizationSubscriptionRead | None:
        response = (
            self.client.table("organization_subscriptions")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .in_("status", list(self.active_subscription_statuses))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return self._coerce_subscription(response.data)

    def get_subscription_by_id(
        self,
        organization_id: UUID | OrganizationContext,
        subscription_id: UUID,
    ) -> OrganizationSubscriptionRead | None:
        response = (
            self.client.table("organization_subscriptions")
            .select("*")
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(subscription_id))
            .limit(1)
            .execute()
        )
        return self._coerce_subscription(response.data)

    def list_subscriptions(
        self,
        organization_id: UUID | OrganizationContext,
        filters: SubscriptionFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[OrganizationSubscriptionRead]:
        query = (
            self.client.table("organization_subscriptions")
            .select("*", count="exact")
            .eq("organization_id", str(self._organization_id(organization_id)))
        )
        query = self._apply_subscription_filters(query, filters)
        query = self._apply_sort(query, sort, self.subscription_sortable_fields)
        return self._page_subscriptions(query, pagination)

    def create_subscription(
        self,
        organization_id: UUID | OrganizationContext,
        payload: dict[str, Any] | BaseModel,
    ) -> OrganizationSubscriptionRead:
        data = self._dump_payload(payload)
        data["organization_id"] = str(self._organization_id(organization_id))
        response = self.client.table("organization_subscriptions").insert(data).execute()
        row = self._first_row(response.data)
        if not row:
            raise LookupError("organization_subscriptions mutation returned no row")
        return OrganizationSubscriptionRead.model_validate(row)

    def update_subscription(
        self,
        organization_id: UUID | OrganizationContext,
        subscription_id: UUID,
        payload: dict[str, Any] | BaseModel,
    ) -> OrganizationSubscriptionRead | None:
        data = self._dump_payload(payload)
        if not data:
            return self.get_subscription_by_id(organization_id, subscription_id)
        response = (
            self.client.table("organization_subscriptions")
            .update(data)
            .eq("organization_id", str(self._organization_id(organization_id)))
            .eq("id", str(subscription_id))
            .execute()
        )
        return self._coerce_subscription(response.data)

    def list_plans(
        self,
        filters: SubscriptionFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[dict[str, Any]]:
        query = self.client.table("subscription_plans").select("*", count="exact")
        query = self._apply_plan_filters(query, filters)
        query = self._apply_sort(query, sort, self.plan_sortable_fields)
        return self._page_dicts(query, pagination)

    def get_plan_by_id(self, plan_id: UUID) -> dict[str, Any] | None:
        response = (
            self.client.table("subscription_plans")
            .select("*")
            .eq("id", str(plan_id))
            .limit(1)
            .execute()
        )
        return self._first_row(response.data) or None

    def get_plan_by_slug(self, slug: str) -> dict[str, Any] | None:
        response = (
            self.client.table("subscription_plans")
            .select("*")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        return self._first_row(response.data) or None

    def get_plan_limits(
        self,
        organization_id: UUID | OrganizationContext,
    ) -> SubscriptionPlanLimits | None:
        subscription = self.get_active_subscription(organization_id)
        if subscription is None:
            return None
        plan = self.get_plan_by_id(subscription.subscription_plan_id)
        if plan is None:
            return None
        return SubscriptionPlanLimits(
            subscription_plan_id=plan["id"],
            subscription_plan_name=plan["name"],
            subscription_plan_slug=plan["slug"],
            monthly_message_limit=plan["monthly_message_limit"],
            monthly_ai_request_limit=plan["monthly_ai_request_limit"],
            monthly_token_limit=plan["monthly_token_limit"],
        )

    def _apply_plan_filters(self, query, filters: SubscriptionFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.eq("status", self._serialize(filters.status))
        if filters.plan_slug is not None:
            query = query.eq("slug", filters.plan_slug)
        return self._apply_time_filters(query, filters)

    def _apply_subscription_filters(self, query, filters: SubscriptionFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.eq("status", self._serialize(filters.status))
        return self._apply_time_filters(query, filters)

    def _apply_time_filters(self, query, filters: SubscriptionFilters):
        for attr_name, column_name, operator in (
            ("created_from", "created_at", "gte"),
            ("created_to", "created_at", "lte"),
            ("updated_from", "updated_at", "gte"),
            ("updated_to", "updated_at", "lte"),
        ):
            value = getattr(filters, attr_name, None)
            if value is not None:
                query = getattr(query, operator)(column_name, self._serialize(value))
        return query

    def _apply_sort(self, query, sort: SortOptions | None, sortable_fields: set[str]):
        sort = sort or SortOptions()
        sort_field = sort.field if sort.field in sortable_fields else "created_at"
        return query.order(sort_field, desc=sort.direction == SortDirection.DESC)

    def _page_subscriptions(
        self,
        query,
        pagination: PaginationOptions | None = None,
    ) -> RepositoryPage[OrganizationSubscriptionRead]:
        pagination = pagination or PaginationOptions()
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count if response.count is not None else len(rows))
        return RepositoryPage(
            items=[OrganizationSubscriptionRead.model_validate(row) for row in rows],
            total=total,
            page=pagination.page or ((offset // max(limit, 1)) + 1),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def _page_dicts(self, query, pagination: PaginationOptions | None = None) -> RepositoryPage[dict[str, Any]]:
        pagination = pagination or PaginationOptions()
        offset, limit = pagination.resolve()
        response = query.range(offset, offset + limit - 1).execute()
        rows = response.data or []
        total = int(response.count if response.count is not None else len(rows))
        return RepositoryPage(
            items=rows,
            total=total,
            page=pagination.page or ((offset // max(limit, 1)) + 1),
            page_size=pagination.page_size or limit,
            offset=offset,
            limit=limit,
        )

    def _coerce_subscription(self, data: Any) -> OrganizationSubscriptionRead | None:
        row = self._first_row(data)
        return OrganizationSubscriptionRead.model_validate(row) if row else None

    def _first_row(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            return data
        return {}

    def _dump_payload(self, payload: dict[str, Any] | BaseModel) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw = payload.model_dump(mode="python", exclude_unset=True, exclude_none=True)
        else:
            raw = {key: value for key, value in dict(payload).items() if value is not None}
        return {key: self._serialize(value) for key, value in raw.items()}

    def _organization_id(self, value: UUID | OrganizationContext) -> UUID:
        if isinstance(value, OrganizationContext):
            return value.organization_id
        return value

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        return value

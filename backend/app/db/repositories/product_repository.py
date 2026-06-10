from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, ProductStatus, RepositoryPage
from app.db.models.queries import ProductFilters, SortOptions
from app.db.models.records import ProductCreate, ProductRead, ProductUpdate
from app.db.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository[ProductRead, ProductCreate, ProductUpdate, ProductFilters]):
    table_name = "products"
    read_model = ProductRead
    sortable_fields = {"created_at", "updated_at", "price", "inventory_quantity", "name", "normalized_name"}

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create(self, organization_id: UUID, payload: ProductCreate | dict[str, Any]) -> ProductRead:
        return super().create(organization_id, payload)

    def update(
        self,
        organization_id: UUID,
        record_id: UUID,
        payload: ProductUpdate | dict[str, Any],
        include_deleted: bool = False,
    ) -> ProductRead | None:
        return super().update(organization_id, record_id, payload, include_deleted=include_deleted)

    def list_active(
        self,
        organization_id: UUID,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ProductRead]:
        filters = ProductFilters(status=ProductStatus.ACTIVE)
        return self.list(organization_id, filters=filters, pagination=pagination, sort=sort)

    def search_by_name(
        self,
        organization_id: UUID,
        name_query: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ProductRead]:
        pagination = pagination or PaginationOptions()
        query = self._scoped_select(organization_id).ilike("name", f"%{name_query.strip()}%")
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

    def find_by_normalized_name(self, organization_id: UUID, normalized_name: str) -> ProductRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("normalized_name", self._normalize_text(normalized_name))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self.read_model.model_validate(rows[0]) if rows else None

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

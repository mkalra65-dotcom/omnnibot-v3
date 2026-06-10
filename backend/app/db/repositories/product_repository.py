from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.db.models.common import PaginationOptions, ProductStatus, RepositoryPage
from app.db.models.queries import ProductFilters, SortOptions
from app.db.models.records import ProductCreate, ProductRead, ProductUpdate
from app.db.repositories.base_repository import BaseRepository, OrganizationContext


class ProductRepository(BaseRepository[ProductRead, ProductCreate, ProductUpdate, ProductFilters]):
    table_name = "products"
    read_model = ProductRead
    sortable_fields = {
        "created_at",
        "updated_at",
        "name",
        "normalized_name",
        "price",
        "inventory_quantity",
        "inventory_reserved",
    }

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def list_active(
        self,
        organization_id: UUID | OrganizationContext,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ProductRead]:
        return self.list(
            organization_id,
            filters=ProductFilters(status=ProductStatus.ACTIVE),
            pagination=pagination,
            sort=sort,
        )

    def list_by_category(
        self,
        organization_id: UUID | OrganizationContext,
        category: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ProductRead]:
        return self.list(
            organization_id,
            filters=ProductFilters(category=category),
            pagination=pagination,
            sort=sort,
        )

    def find_by_sku(
        self,
        organization_id: UUID | OrganizationContext,
        sku: str,
    ) -> ProductRead | None:
        response = self._scoped_select(organization_id).eq("sku", sku).limit(1).execute()
        return self._coerce_optional(response.data)

    def find_by_normalized_name(
        self,
        organization_id: UUID | OrganizationContext,
        normalized_name: str,
    ) -> ProductRead | None:
        response = (
            self._scoped_select(organization_id)
            .eq("normalized_name", self._normalize_text(normalized_name))
            .limit(1)
            .execute()
        )
        return self._coerce_optional(response.data)

    def search_by_name(
        self,
        organization_id: UUID | OrganizationContext,
        name_query: str,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[ProductRead]:
        query = self._scoped_select(organization_id).ilike("name", f"%{name_query.strip()}%")
        return self._list_with_query(query, pagination=pagination, sort=sort)

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

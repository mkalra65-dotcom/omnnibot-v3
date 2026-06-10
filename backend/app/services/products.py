from uuid import UUID

from app.api.dependencies import TenantContext
from app.schemas.products import ProductCreate, ProductUpdate
from app.services.base import BaseService


class ProductService(BaseService):
    async def create(self, tenant: TenantContext, payload: ProductCreate) -> None:
        self.not_implemented("Product creation logic is not implemented yet")

    async def list(self, tenant: TenantContext) -> None:
        self.not_implemented("Product listing logic is not implemented yet")

    async def get(self, tenant: TenantContext, product_id: UUID) -> None:
        self.not_implemented("Product retrieval logic is not implemented yet")

    async def update(
        self,
        tenant: TenantContext,
        product_id: UUID,
        payload: ProductUpdate,
    ) -> None:
        self.not_implemented("Product update logic is not implemented yet")

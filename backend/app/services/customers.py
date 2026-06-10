from uuid import UUID

from app.api.dependencies import TenantContext
from app.schemas.customers import CustomerCreate, CustomerUpdate
from app.services.base import BaseService


class CustomerService(BaseService):
    async def create(self, tenant: TenantContext, payload: CustomerCreate) -> None:
        self.not_implemented("Customer creation logic is not implemented yet")

    async def list(self, tenant: TenantContext) -> None:
        self.not_implemented("Customer listing logic is not implemented yet")

    async def get(self, tenant: TenantContext, customer_id: UUID) -> None:
        self.not_implemented("Customer retrieval logic is not implemented yet")

    async def update(
        self,
        tenant: TenantContext,
        customer_id: UUID,
        payload: CustomerUpdate,
    ) -> None:
        self.not_implemented("Customer update logic is not implemented yet")

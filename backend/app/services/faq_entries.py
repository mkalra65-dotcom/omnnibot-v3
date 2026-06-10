from uuid import UUID

from app.api.dependencies import TenantContext
from app.schemas.faq_entries import FaqEntryCreate, FaqEntryUpdate
from app.services.base import BaseService


class FaqEntryService(BaseService):
    async def create(self, tenant: TenantContext, payload: FaqEntryCreate) -> None:
        self.not_implemented("FAQ entry creation logic is not implemented yet")

    async def list(self, tenant: TenantContext) -> None:
        self.not_implemented("FAQ entry listing logic is not implemented yet")

    async def get(self, tenant: TenantContext, faq_entry_id: UUID) -> None:
        self.not_implemented("FAQ entry retrieval logic is not implemented yet")

    async def update(
        self,
        tenant: TenantContext,
        faq_entry_id: UUID,
        payload: FaqEntryUpdate,
    ) -> None:
        self.not_implemented("FAQ entry update logic is not implemented yet")

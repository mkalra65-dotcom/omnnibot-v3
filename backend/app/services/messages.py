from uuid import UUID

from app.api.dependencies import TenantContext
from app.schemas.messages import MessageCreate, MessageUpdate
from app.services.base import BaseService


class MessageService(BaseService):
    async def create(self, tenant: TenantContext, payload: MessageCreate) -> None:
        self.not_implemented("Message creation logic is not implemented yet")

    async def list(self, tenant: TenantContext) -> None:
        self.not_implemented("Message listing logic is not implemented yet")

    async def get(self, tenant: TenantContext, message_id: UUID) -> None:
        self.not_implemented("Message retrieval logic is not implemented yet")

    async def update(
        self,
        tenant: TenantContext,
        message_id: UUID,
        payload: MessageUpdate,
    ) -> None:
        self.not_implemented("Message update logic is not implemented yet")

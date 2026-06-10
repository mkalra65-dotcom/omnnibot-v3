from uuid import UUID

from app.api.dependencies import TenantContext
from app.schemas.conversations import ConversationCreate, ConversationUpdate
from app.services.base import BaseService


class ConversationService(BaseService):
    async def create(self, tenant: TenantContext, payload: ConversationCreate) -> None:
        self.not_implemented("Conversation creation logic is not implemented yet")

    async def list(self, tenant: TenantContext) -> None:
        self.not_implemented("Conversation listing logic is not implemented yet")

    async def get(self, tenant: TenantContext, conversation_id: UUID) -> None:
        self.not_implemented("Conversation retrieval logic is not implemented yet")

    async def update(
        self,
        tenant: TenantContext,
        conversation_id: UUID,
        payload: ConversationUpdate,
    ) -> None:
        self.not_implemented("Conversation update logic is not implemented yet")

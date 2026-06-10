from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import TenantContext, get_tenant_context
from app.schemas.conversations import ConversationCreate, ConversationUpdate
from app.services.conversations import ConversationService

router = APIRouter()


def get_conversation_service() -> ConversationService:
    return ConversationService()


@router.post("", status_code=501)
async def create_conversation(
    payload: ConversationCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    await service.create(tenant, payload)


@router.get("", status_code=501)
async def list_conversations(
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    await service.list(tenant)


@router.get("/{conversation_id}", status_code=501)
async def get_conversation(
    conversation_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    await service.get(tenant, conversation_id)


@router.patch("/{conversation_id}", status_code=501)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    await service.update(tenant, conversation_id, payload)

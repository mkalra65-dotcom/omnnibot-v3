from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import TenantContext, get_tenant_context
from app.schemas.messages import MessageCreate, MessageUpdate
from app.services.messages import MessageService

router = APIRouter()


def get_message_service() -> MessageService:
    return MessageService()


@router.post("", status_code=501)
async def create_message(
    payload: MessageCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> None:
    await service.create(tenant, payload)


@router.get("", status_code=501)
async def list_messages(
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> None:
    await service.list(tenant)


@router.get("/{message_id}", status_code=501)
async def get_message(
    message_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> None:
    await service.get(tenant, message_id)


@router.patch("/{message_id}", status_code=501)
async def update_message(
    message_id: UUID,
    payload: MessageUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> None:
    await service.update(tenant, message_id, payload)

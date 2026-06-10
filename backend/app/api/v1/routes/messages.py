from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_tenant_context
from app.db.models.common import ChannelType, MessageStatus, PaginationOptions, SortDirection
from app.db.models.queries import MessageFilters, SortOptions
from app.db.models.records import MessageRead
from app.schemas.messages import MessageCreateRequest, MessageListResponse
from app.services.messages import MessageService
from app.services.organization_access import TenantContext

router = APIRouter()


def get_message_service() -> MessageService:
    return MessageService()


@router.post("", response_model=MessageRead)
async def create_message(
    payload: MessageCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.create(tenant, payload)


@router.get("/conversation/{conversation_id}", response_model=MessageListResponse)
async def list_messages_by_conversation(
    conversation_id: UUID,
    status: MessageStatus | None = None,
    channel: ChannelType | None = None,
    direction: str | None = None,
    sender_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_field: str = "created_at",
    sort_direction: SortDirection = SortDirection.ASC,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
):
    return await service.list_by_conversation(
        tenant,
        conversation_id=conversation_id,
        filters=MessageFilters(
            status=status,
            channel=channel,
            direction=direction,
            sender_type=sender_type,
        ),
        pagination=PaginationOptions(page=page, page_size=page_size),
        sort=SortOptions(field=sort_field, direction=sort_direction),
    )


@router.get("/external-message/{external_message_id}", response_model=MessageRead)
async def get_message_by_external_message_id(
    external_message_id: str,
    channel: ChannelType | None = None,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.get_by_external_message_id(
        tenant,
        external_message_id=external_message_id,
        channel=channel,
    )


@router.get("/external-event/{external_event_id}", response_model=MessageRead)
async def get_message_by_external_event_id(
    external_event_id: str,
    channel: ChannelType | None = None,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.get_by_external_event_id(
        tenant,
        external_event_id=external_event_id,
        channel=channel,
    )


@router.get("/webhook-delivery/{webhook_delivery_id}", response_model=MessageRead)
async def get_message_by_webhook_delivery_id(
    webhook_delivery_id: str,
    channel: ChannelType | None = None,
    tenant: TenantContext = Depends(get_tenant_context),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.get_by_webhook_delivery_id(
        tenant,
        webhook_delivery_id=webhook_delivery_id,
        channel=channel,
    )

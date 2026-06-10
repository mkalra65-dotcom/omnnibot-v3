from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_tenant_context
from app.db.models.common import ChannelType, ConversationStatus, PaginationOptions, SortDirection
from app.db.models.queries import ConversationFilters, SortOptions
from app.db.models.records import ConversationRead
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationListResponse,
    FollowupTimestampsUpdate,
    HandoffStatusUpdate,
)
from app.services.conversations import ConversationService
from app.services.organization_access import TenantContext

router = APIRouter()


def get_conversation_service() -> ConversationService:
    return ConversationService()


@router.post("", response_model=ConversationRead)
async def create_conversation(
    payload: ConversationCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    return await service.create(tenant, payload)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    status: ConversationStatus | None = None,
    channel: ChannelType | None = None,
    handoff_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_field: str = "updated_at",
    sort_direction: SortDirection = SortDirection.DESC,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
):
    return await service.list(
        tenant,
        filters=ConversationFilters(
            status=status,
            channel=channel,
            handoff_status=handoff_status,
        ),
        pagination=PaginationOptions(page=page, page_size=page_size),
        sort=SortOptions(field=sort_field, direction=sort_direction),
    )


@router.get("/customer/{customer_id}", response_model=ConversationListResponse)
async def list_conversations_by_customer(
    customer_id: UUID,
    status: ConversationStatus | None = None,
    channel: ChannelType | None = None,
    handoff_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_field: str = "updated_at",
    sort_direction: SortDirection = SortDirection.DESC,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
):
    return await service.list_by_customer(
        tenant,
        customer_id=customer_id,
        filters=ConversationFilters(
            status=status,
            channel=channel,
            handoff_status=handoff_status,
        ),
        pagination=PaginationOptions(page=page, page_size=page_size),
        sort=SortOptions(field=sort_field, direction=sort_direction),
    )


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    return await service.get(tenant, conversation_id)


@router.patch("/{conversation_id}/handoff-status", response_model=ConversationRead)
async def update_handoff_status(
    conversation_id: UUID,
    payload: HandoffStatusUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    return await service.update_handoff_status(
        tenant,
        conversation_id=conversation_id,
        handoff_status=payload.handoff_status,
    )


@router.patch("/{conversation_id}/followup-timestamps", response_model=ConversationRead)
async def update_followup_timestamps(
    conversation_id: UUID,
    payload: FollowupTimestampsUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    return await service.update_followup_timestamps(
        tenant,
        conversation_id=conversation_id,
        payload=payload,
    )

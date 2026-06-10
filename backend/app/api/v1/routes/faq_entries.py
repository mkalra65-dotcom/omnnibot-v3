from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import TenantContext, get_tenant_context
from app.schemas.faq_entries import FaqEntryCreate, FaqEntryUpdate
from app.services.faq_entries import FaqEntryService

router = APIRouter()


def get_faq_entry_service() -> FaqEntryService:
    return FaqEntryService()


@router.post("", status_code=501)
async def create_faq_entry(
    payload: FaqEntryCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: FaqEntryService = Depends(get_faq_entry_service),
) -> None:
    await service.create(tenant, payload)


@router.get("", status_code=501)
async def list_faq_entries(
    tenant: TenantContext = Depends(get_tenant_context),
    service: FaqEntryService = Depends(get_faq_entry_service),
) -> None:
    await service.list(tenant)


@router.get("/{faq_entry_id}", status_code=501)
async def get_faq_entry(
    faq_entry_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: FaqEntryService = Depends(get_faq_entry_service),
) -> None:
    await service.get(tenant, faq_entry_id)


@router.patch("/{faq_entry_id}", status_code=501)
async def update_faq_entry(
    faq_entry_id: UUID,
    payload: FaqEntryUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: FaqEntryService = Depends(get_faq_entry_service),
) -> None:
    await service.update(tenant, faq_entry_id, payload)

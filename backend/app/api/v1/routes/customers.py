from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_tenant_context
from app.db.models.common import CustomerStatus, LeadStage, PaginationOptions, SortDirection
from app.db.models.queries import CustomerFilters, SortOptions
from app.db.models.records import CustomerIdentityRead, CustomerRead
from app.schemas.customers import (
    CustomerCreateRequest,
    CustomerIdentityCreateRequest,
    CustomerListResponse,
    CustomerUpdateRequest,
)
from app.services.customers import CustomerService
from app.services.organization_access import TenantContext

router = APIRouter()


def get_customer_service() -> CustomerService:
    return CustomerService()


@router.post("", response_model=CustomerRead)
async def create_customer(
    payload: CustomerCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> CustomerRead:
    return await service.create(tenant, payload)


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    status: CustomerStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_field: str = "created_at",
    sort_direction: SortDirection = SortDirection.DESC,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
):
    return await service.list(
        tenant,
        filters=CustomerFilters(status=status),
        pagination=PaginationOptions(page=page, page_size=page_size),
        sort=SortOptions(field=sort_field, direction=sort_direction),
    )


@router.get("/lead-stage/{lead_stage}", response_model=CustomerListResponse)
async def list_customers_by_lead_stage(
    lead_stage: LeadStage,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_field: str = "created_at",
    sort_direction: SortDirection = SortDirection.DESC,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
):
    return await service.list_by_lead_stage(
        tenant,
        lead_stage=lead_stage,
        pagination=PaginationOptions(page=page, page_size=page_size),
        sort=SortOptions(field=sort_field, direction=sort_direction),
    )


@router.get("/by-identity", response_model=CustomerRead)
async def find_customer_by_identity(
    provider: str,
    provider_user_id: str | None = None,
    provider_username: str | None = None,
    provider_phone: str | None = None,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> CustomerRead:
    return await service.find_by_identity(
        tenant,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_username=provider_username,
        provider_phone=provider_phone,
    )


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> CustomerRead:
    return await service.get(tenant, customer_id)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> CustomerRead:
    return await service.update(tenant, customer_id, payload)


@router.post("/{customer_id}/identities", response_model=CustomerIdentityRead)
async def create_customer_identity(
    customer_id: UUID,
    payload: CustomerIdentityCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> CustomerIdentityRead:
    return await service.create_identity(tenant, customer_id, payload)

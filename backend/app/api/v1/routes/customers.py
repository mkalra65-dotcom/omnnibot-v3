from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import TenantContext, get_tenant_context
from app.schemas.customers import CustomerCreate, CustomerUpdate
from app.services.customers import CustomerService

router = APIRouter()


def get_customer_service() -> CustomerService:
    return CustomerService()


@router.post("", status_code=501)
async def create_customer(
    payload: CustomerCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> None:
    await service.create(tenant, payload)


@router.get("", status_code=501)
async def list_customers(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> None:
    await service.list(tenant)


@router.get("/{customer_id}", status_code=501)
async def get_customer(
    customer_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> None:
    await service.get(tenant, customer_id)


@router.patch("/{customer_id}", status_code=501)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CustomerService = Depends(get_customer_service),
) -> None:
    await service.update(tenant, customer_id, payload)

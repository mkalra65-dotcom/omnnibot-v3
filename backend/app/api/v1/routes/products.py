from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import TenantContext, get_tenant_context
from app.schemas.products import ProductCreate, ProductUpdate
from app.services.products import ProductService

router = APIRouter()


def get_product_service() -> ProductService:
    return ProductService()


@router.post("", status_code=501)
async def create_product(
    payload: ProductCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ProductService = Depends(get_product_service),
) -> None:
    await service.create(tenant, payload)


@router.get("", status_code=501)
async def list_products(
    tenant: TenantContext = Depends(get_tenant_context),
    service: ProductService = Depends(get_product_service),
) -> None:
    await service.list(tenant)


@router.get("/{product_id}", status_code=501)
async def get_product(
    product_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ProductService = Depends(get_product_service),
) -> None:
    await service.get(tenant, product_id)


@router.patch("/{product_id}", status_code=501)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ProductService = Depends(get_product_service),
) -> None:
    await service.update(tenant, product_id, payload)

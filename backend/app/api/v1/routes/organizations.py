from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.organizations import OrganizationCreate, OrganizationUpdate
from app.services.organizations import OrganizationService

router = APIRouter()


def get_organization_service() -> OrganizationService:
    return OrganizationService()


@router.post("", status_code=501)
async def create_organization(
    payload: OrganizationCreate,
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.create(payload)


@router.get("", status_code=501)
async def list_organizations(
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.list()


@router.get("/{organization_id}", status_code=501)
async def get_organization(
    organization_id: UUID,
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.get(organization_id)


@router.patch("/{organization_id}", status_code=501)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.update(organization_id, payload)

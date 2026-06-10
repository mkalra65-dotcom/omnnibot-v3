from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.memberships import MembershipCreate, MembershipUpdate
from app.services.memberships import MembershipService

router = APIRouter()


def get_membership_service() -> MembershipService:
    return MembershipService()


@router.post("", status_code=501)
async def create_membership(
    payload: MembershipCreate,
    service: MembershipService = Depends(get_membership_service),
) -> None:
    await service.create(payload)


@router.get("", status_code=501)
async def list_memberships(
    service: MembershipService = Depends(get_membership_service),
) -> None:
    await service.list()


@router.get("/{membership_id}", status_code=501)
async def get_membership(
    membership_id: UUID,
    service: MembershipService = Depends(get_membership_service),
) -> None:
    await service.get(membership_id)


@router.patch("/{membership_id}", status_code=501)
async def update_membership(
    membership_id: UUID,
    payload: MembershipUpdate,
    service: MembershipService = Depends(get_membership_service),
) -> None:
    await service.update(membership_id, payload)

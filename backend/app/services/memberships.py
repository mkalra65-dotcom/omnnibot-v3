from uuid import UUID

from app.schemas.memberships import MembershipCreate, MembershipUpdate
from app.services.base import BaseService


class MembershipService(BaseService):
    async def create(self, payload: MembershipCreate) -> None:
        self.not_implemented("Membership creation logic is not implemented yet")

    async def list(self) -> None:
        self.not_implemented("Membership listing logic is not implemented yet")

    async def get(self, membership_id: UUID) -> None:
        self.not_implemented("Membership retrieval logic is not implemented yet")

    async def update(self, membership_id: UUID, payload: MembershipUpdate) -> None:
        self.not_implemented("Membership update logic is not implemented yet")

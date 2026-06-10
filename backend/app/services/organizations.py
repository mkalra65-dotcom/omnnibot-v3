from uuid import UUID

from app.schemas.organizations import OrganizationCreate, OrganizationUpdate
from app.services.base import BaseService


class OrganizationService(BaseService):
    async def create(self, payload: OrganizationCreate) -> None:
        self.not_implemented("Organization creation logic is not implemented yet")

    async def list(self) -> None:
        self.not_implemented("Organization listing logic is not implemented yet")

    async def get(self, organization_id: UUID) -> None:
        self.not_implemented("Organization retrieval logic is not implemented yet")

    async def update(self, organization_id: UUID, payload: OrganizationUpdate) -> None:
        self.not_implemented("Organization update logic is not implemented yet")

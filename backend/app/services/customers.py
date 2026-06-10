from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import LeadStage, PaginationOptions, RepositoryPage
from app.db.models.queries import CustomerFilters, SortOptions
from app.db.models.records import CustomerCreate, CustomerIdentityRead, CustomerRead, CustomerUpdate, LeadEventCreate
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.customer_repository import CustomerRepository
from app.db.repositories.lead_event_repository import LeadEventRepository
from app.schemas.customers import CustomerCreateRequest, CustomerIdentityCreateRequest, CustomerUpdateRequest
from app.services.base import BaseService
from app.services.organization_access import OrganizationAccessService, TenantContext


CRM_WRITE_ROLES = {"agent", "manager", "admin", "owner"}
CRM_PRIVILEGED_ROLES = {"manager", "admin", "owner"}


class CustomerService(BaseService):
    def __init__(self, supabase_factory: SupabaseClientFactory | None = None) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        service_client = self.supabase_factory.get_service_client()
        self.repository = CustomerRepository(service_client)
        self.lead_event_repository = LeadEventRepository(service_client)
        self.organization_access_service = OrganizationAccessService(self.supabase_factory)

    async def create(self, tenant: TenantContext, payload: CustomerCreateRequest) -> CustomerRead:
        self._require_role(tenant, CRM_WRITE_ROLES)
        return self.repository.create(
            self._repository_context(tenant),
            CustomerCreate(**payload.model_dump(mode="python", exclude_unset=True)),
        )

    async def list(
        self,
        tenant: TenantContext,
        filters: CustomerFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        return self.repository.list_by_organization(
            self._repository_context(tenant),
            filters=filters,
            pagination=pagination,
            sort=sort,
        )

    async def get(self, tenant: TenantContext, customer_id: UUID) -> CustomerRead:
        customer = self.repository.get_by_id(self._repository_context(tenant), customer_id)
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )
        return customer

    async def update(
        self,
        tenant: TenantContext,
        customer_id: UUID,
        payload: CustomerUpdateRequest,
    ) -> CustomerRead:
        update_data = payload.model_dump(mode="python", exclude_unset=True, exclude_none=True)
        privileged_fields = {"lead_stage", "lead_score"}
        if privileged_fields.intersection(update_data):
            self._require_role(tenant, CRM_PRIVILEGED_ROLES)
        else:
            self._require_role(tenant, CRM_WRITE_ROLES)

        context = self._repository_context(tenant)
        existing = self.repository.get_by_id(context, customer_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        customer = self.repository.update(context, customer_id, CustomerUpdate(**update_data))
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        if payload.lead_stage is not None and payload.lead_stage != existing.lead_stage:
            self.lead_event_repository.create(
                context,
                LeadEventCreate(
                    customer_id=customer_id,
                    lead_stage=payload.lead_stage,
                    event_type=self._lead_event_type(payload.lead_stage),
                    metadata={
                        "source": "dashboard",
                        "actor_user_id": str(tenant.user_id),
                        "actor_membership_id": str(tenant.membership_id),
                        "old_lead_stage": existing.lead_stage.value,
                        "new_lead_stage": payload.lead_stage.value,
                    },
                ),
            )
        return customer

    async def list_by_lead_stage(
        self,
        tenant: TenantContext,
        lead_stage: LeadStage,
        pagination: PaginationOptions | None = None,
        sort: SortOptions | None = None,
    ) -> RepositoryPage[CustomerRead]:
        return self.repository.list_by_lead_stage(
            self._repository_context(tenant),
            lead_stage=lead_stage,
            pagination=pagination,
            sort=sort,
        )

    async def create_identity(
        self,
        tenant: TenantContext,
        customer_id: UUID,
        payload: CustomerIdentityCreateRequest,
    ) -> CustomerIdentityRead:
        self._require_role(tenant, CRM_PRIVILEGED_ROLES)
        if not any((payload.provider_user_id, payload.provider_username, payload.provider_phone)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one provider identifier is required",
            )

        context = self._repository_context(tenant)
        await self.get(tenant, customer_id)
        existing = self.repository.find_identity(
            context,
            provider=payload.provider,
            provider_user_id=payload.provider_user_id,
            provider_username=payload.provider_username,
            provider_phone=payload.provider_phone,
        )
        if existing is not None:
            return existing

        return self.repository.create_identity(
            context,
            {
                "customer_id": customer_id,
                "provider": payload.provider,
                "provider_user_id": payload.provider_user_id,
                "provider_username": payload.provider_username,
                "provider_phone": payload.provider_phone,
                "metadata": {"source": "dashboard"},
            },
        )

    async def find_by_identity(
        self,
        tenant: TenantContext,
        provider: str,
        provider_user_id: str | None = None,
        provider_username: str | None = None,
        provider_phone: str | None = None,
    ) -> CustomerRead:
        customer = self.repository.find_by_identity(
            self._repository_context(tenant),
            provider=provider,
            provider_user_id=provider_user_id,
            provider_username=provider_username,
            provider_phone=provider_phone,
        )
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer identity not found",
            )
        return customer

    def _require_role(self, tenant: TenantContext, allowed_roles: set[str]) -> None:
        self.organization_access_service.require_role(
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            allowed_roles=allowed_roles,
        )

    def _repository_context(self, tenant: TenantContext) -> OrganizationContext:
        return OrganizationContext(
            organization_id=tenant.organization_id,
            user_id=tenant.user_id,
            membership_id=tenant.membership_id,
            role=tenant.role,
        )

    def _lead_event_type(self, lead_stage: LeadStage) -> str:
        return {
            LeadStage.NEW: "LEAD_CREATED",
            LeadStage.ENGAGED: "PRICE_DISCUSSION",
            LeadStage.INTERESTED: "PRODUCT_INTEREST",
            LeadStage.PAYMENT_SENT: "PAYMENT_SENT",
            LeadStage.WON: "WON",
            LeadStage.LOST: "LOST",
        }[lead_stage]

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from postgrest.exceptions import APIError

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.records import CustomerCreate, CustomerIdentityCreate, CustomerIdentityRead, CustomerRead
from app.db.repositories.customer_repository import CustomerRepository
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolution
from app.services.whatsapp_payloads import MetaWhatsAppWebhookPayload

WHATSAPP_PROVIDER = "whatsapp"


class WhatsAppCustomerIdentityResolutionError(LookupError):
    pass


class WhatsAppCustomerIdentityInputError(WhatsAppCustomerIdentityResolutionError):
    pass


class WhatsAppCustomerIdentityAmbiguousError(WhatsAppCustomerIdentityResolutionError):
    pass


@dataclass(frozen=True, slots=True)
class WhatsAppCustomerIdentityResolution:
    organization_id: UUID
    provider: str
    wa_id: str
    identity_id: UUID | None
    customer_id: UUID | None
    customer_creation_required: bool

    @classmethod
    def existing(
        cls,
        organization_id: UUID,
        wa_id: str,
        identity: CustomerIdentityRead,
        customer: CustomerRead,
    ) -> WhatsAppCustomerIdentityResolution:
        return cls(
            organization_id=organization_id,
            provider=WHATSAPP_PROVIDER,
            wa_id=wa_id,
            identity_id=identity.id,
            customer_id=customer.id,
            customer_creation_required=False,
        )

    @classmethod
    def missing(
        cls,
        organization_id: UUID,
        wa_id: str,
    ) -> WhatsAppCustomerIdentityResolution:
        return cls(
            organization_id=organization_id,
            provider=WHATSAPP_PROVIDER,
            wa_id=wa_id,
            identity_id=None,
            customer_id=None,
            customer_creation_required=True,
        )

    def as_response(self) -> dict[str, str | bool | None]:
        return {
            "organization_id": str(self.organization_id),
            "provider": self.provider,
            "wa_id": self.wa_id,
            "identity_id": str(self.identity_id) if self.identity_id else None,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "customer_creation_required": self.customer_creation_required,
        }


class WhatsAppCustomerIdentityResolutionService:
    def __init__(
        self,
        repository: CustomerRepository | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self._repository = repository
        self._supabase_factory = supabase_factory

    def resolve(
        self,
        payload: MetaWhatsAppWebhookPayload,
        organization_resolution: WhatsAppOrganizationResolution,
    ) -> WhatsAppCustomerIdentityResolution:
        organization_id = organization_resolution.organization_id
        if organization_id is None:
            raise WhatsAppCustomerIdentityInputError("organization_id is required")

        wa_id = self._single_wa_id(payload)
        identities = self.repository.list_identities_by_provider_user_id(
            organization_id=organization_id,
            provider=WHATSAPP_PROVIDER,
            provider_user_id=wa_id,
            limit=2,
        )

        if len(identities) > 1:
            raise WhatsAppCustomerIdentityAmbiguousError("WhatsApp customer identity is duplicated")
        if not identities:
            return self._create_customer_identity(
                payload=payload,
                organization_resolution=organization_resolution,
                wa_id=wa_id,
            )

        identity = identities[0]
        customer = self.repository.get_by_id(organization_id, identity.customer_id)
        if customer is None:
            raise WhatsAppCustomerIdentityResolutionError(
                "WhatsApp customer identity is missing its linked customer"
            )

        return WhatsAppCustomerIdentityResolution.existing(
            organization_id=organization_id,
            wa_id=wa_id,
            identity=identity,
            customer=customer,
        )

    def _create_customer_identity(
        self,
        *,
        payload: MetaWhatsAppWebhookPayload,
        organization_resolution: WhatsAppOrganizationResolution,
        wa_id: str,
    ) -> WhatsAppCustomerIdentityResolution:
        organization_id = organization_resolution.organization_id
        profile_name = payload.contact_profile_names.get(wa_id)
        customer = self.repository.create(
            organization_id,
            CustomerCreate(
                display_name=profile_name,
                phone_number=wa_id,
                metadata={
                    "source": "whatsapp_webhook",
                    "provider": WHATSAPP_PROVIDER,
                    "wa_id": wa_id,
                    "phone_number_id": organization_resolution.phone_number_id,
                    "whatsapp_business_account_id": organization_resolution.whatsapp_business_account_id,
                    "profile_name": profile_name,
                },
            ),
        )
        try:
            identity = self.repository.create_identity(
                organization_id,
                CustomerIdentityCreate(
                    customer_id=customer.id,
                    provider=WHATSAPP_PROVIDER,
                    provider_user_id=wa_id,
                    metadata={
                        "source": "whatsapp_webhook",
                        "wa_id": wa_id,
                        "phone_number_id": organization_resolution.phone_number_id,
                        "whatsapp_business_account_id": organization_resolution.whatsapp_business_account_id,
                        "profile_name": profile_name,
                    },
                ),
            )
        except APIError as exc:
            if _is_unique_violation(exc):
                identities = self.repository.list_identities_by_provider_user_id(
                    organization_id=organization_id,
                    provider=WHATSAPP_PROVIDER,
                    provider_user_id=wa_id,
                    limit=2,
                )
                if len(identities) == 1:
                    existing_customer = self.repository.get_by_id(organization_id, identities[0].customer_id)
                    if existing_customer is not None:
                        return WhatsAppCustomerIdentityResolution.existing(
                            organization_id=organization_id,
                            wa_id=wa_id,
                            identity=identities[0],
                            customer=existing_customer,
                        )
            raise

        return WhatsAppCustomerIdentityResolution.existing(
            organization_id=organization_id,
            wa_id=wa_id,
            identity=identity,
            customer=customer,
        )

    def _single_wa_id(self, payload: MetaWhatsAppWebhookPayload) -> str:
        wa_ids = tuple(dict.fromkeys(payload.wa_ids))
        if not wa_ids:
            raise WhatsAppCustomerIdentityInputError("WhatsApp payload is missing wa_id")
        if len(wa_ids) > 1:
            raise WhatsAppCustomerIdentityInputError("WhatsApp payload contains multiple wa_id values")

        wa_id = wa_ids[0].strip()
        if not wa_id:
            raise WhatsAppCustomerIdentityInputError("WhatsApp wa_id is empty")
        if not wa_id.isdigit():
            raise WhatsAppCustomerIdentityInputError("WhatsApp wa_id is malformed")
        return wa_id

    @property
    def repository(self) -> CustomerRepository:
        if self._repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._repository = CustomerRepository(factory.get_service_client())
        return self._repository


def _is_unique_violation(exc: APIError) -> bool:
    return exc.json().get("code") == "23505"

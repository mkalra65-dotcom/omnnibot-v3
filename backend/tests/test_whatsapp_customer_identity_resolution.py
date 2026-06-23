from pathlib import Path
from uuid import UUID

import pytest

from app.db.models.common import CustomerStatus, LeadStage
from app.db.models.records import CustomerIdentityRead, CustomerRead
from app.services.whatsapp_customer_identity_resolution import (
    WhatsAppCustomerIdentityAmbiguousError,
    WhatsAppCustomerIdentityInputError,
    WhatsAppCustomerIdentityResolutionService,
)
from app.services.whatsapp_organization_resolution import WhatsAppOrganizationResolution
from app.services.whatsapp_payloads import MetaWhatsAppWebhookPayload, parse_meta_whatsapp_webhook


FIXTURES_DIR = Path(__file__).parent / "fixtures"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
ACCOUNT_ID = UUID("33333333-3333-3333-3333-333333333333")
CUSTOMER_ID = UUID("44444444-4444-4444-4444-444444444444")
OTHER_CUSTOMER_ID = UUID("55555555-5555-5555-5555-555555555555")
IDENTITY_ID = UUID("66666666-6666-6666-6666-666666666666")
OTHER_IDENTITY_ID = UUID("77777777-7777-7777-7777-777777777777")
WA_ID = "919876543210"


class FakeCustomerRepository:
    def __init__(
        self,
        identities: list[CustomerIdentityRead] | None = None,
        customers: list[CustomerRead] | None = None,
    ) -> None:
        self.identities = identities or []
        self.customers = customers or []
        self.lookup_organization_ids: list[UUID] = []

    def list_identities_by_provider_user_id(
        self,
        organization_id: UUID,
        provider: str,
        provider_user_id: str,
        limit: int = 2,
    ) -> list[CustomerIdentityRead]:
        self.lookup_organization_ids.append(organization_id)
        matches = [
            identity
            for identity in self.identities
            if identity.organization_id == organization_id
            and identity.provider == provider
            and identity.provider_user_id == provider_user_id
        ]
        return matches[:limit]

    def get_by_id(self, organization_id: UUID, customer_id: UUID) -> CustomerRead | None:
        for customer in self.customers:
            if customer.organization_id == organization_id and customer.id == customer_id:
                return customer
        return None


def test_resolves_existing_identity() -> None:
    repository = FakeCustomerRepository(
        identities=[_identity()],
        customers=[_customer()],
    )
    service = WhatsAppCustomerIdentityResolutionService(repository=repository)

    resolution = service.resolve(_payload(), _organization_resolution())

    assert resolution.organization_id == ORGANIZATION_ID
    assert resolution.provider == "whatsapp"
    assert resolution.wa_id == WA_ID
    assert resolution.identity_id == IDENTITY_ID
    assert resolution.customer_id == CUSTOMER_ID
    assert resolution.customer_creation_required is False


def test_missing_identity_returns_creation_required_without_persistence() -> None:
    repository = FakeCustomerRepository()
    service = WhatsAppCustomerIdentityResolutionService(repository=repository)

    resolution = service.resolve(_payload(), _organization_resolution())

    assert resolution.identity_id is None
    assert resolution.customer_id is None
    assert resolution.customer_creation_required is True
    assert repository.identities == []
    assert repository.customers == []


def test_same_wa_id_in_different_organization_does_not_resolve() -> None:
    repository = FakeCustomerRepository(
        identities=[
            _identity(
                id=OTHER_IDENTITY_ID,
                organization_id=OTHER_ORGANIZATION_ID,
                customer_id=OTHER_CUSTOMER_ID,
            )
        ],
        customers=[
            _customer(id=OTHER_CUSTOMER_ID, organization_id=OTHER_ORGANIZATION_ID)
        ],
    )
    service = WhatsAppCustomerIdentityResolutionService(repository=repository)

    resolution = service.resolve(_payload(), _organization_resolution())

    assert resolution.customer_creation_required is True
    assert repository.lookup_organization_ids == [ORGANIZATION_ID]


def test_rejects_malformed_wa_id() -> None:
    service = WhatsAppCustomerIdentityResolutionService(repository=FakeCustomerRepository())

    with pytest.raises(WhatsAppCustomerIdentityInputError):
        service.resolve(_payload(wa_ids=("wa-919876543210",)), _organization_resolution())


def test_rejects_empty_wa_id() -> None:
    service = WhatsAppCustomerIdentityResolutionService(repository=FakeCustomerRepository())

    with pytest.raises(WhatsAppCustomerIdentityInputError):
        service.resolve(_payload(wa_ids=("",)), _organization_resolution())


def test_rejects_duplicate_identity_records() -> None:
    repository = FakeCustomerRepository(
        identities=[
            _identity(),
            _identity(id=OTHER_IDENTITY_ID, customer_id=OTHER_CUSTOMER_ID),
        ],
        customers=[_customer(), _customer(id=OTHER_CUSTOMER_ID)],
    )
    service = WhatsAppCustomerIdentityResolutionService(repository=repository)

    with pytest.raises(WhatsAppCustomerIdentityAmbiguousError):
        service.resolve(_payload(), _organization_resolution())


def test_rejects_missing_organization_id() -> None:
    service = WhatsAppCustomerIdentityResolutionService(repository=FakeCustomerRepository())
    organization_resolution = WhatsAppOrganizationResolution(
        organization_id=None,  # type: ignore[arg-type]
        account_id=ACCOUNT_ID,
        phone_number_id="PHONE_NUMBER_123",
        whatsapp_business_account_id="WABA_123",
        provider_metadata={},
    )

    with pytest.raises(WhatsAppCustomerIdentityInputError):
        service.resolve(_payload(), organization_resolution)


def test_parse_meta_payload_extracts_wa_id() -> None:
    payload = parse_meta_whatsapp_webhook(
        (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    )

    assert payload.wa_ids == (WA_ID,)
    assert payload.has_inbound_messages is True


def _payload(wa_ids: tuple[str, ...] = (WA_ID,)) -> MetaWhatsAppWebhookPayload:
    return MetaWhatsAppWebhookPayload(
        phone_number_id="PHONE_NUMBER_123",
        whatsapp_business_account_id="WABA_123",
        wa_ids=wa_ids,
        has_inbound_messages=True,
        event_type="message",
        external_event_id="wamid.test",
        provider_metadata={},
    )


def _organization_resolution(
    organization_id: UUID = ORGANIZATION_ID,
) -> WhatsAppOrganizationResolution:
    return WhatsAppOrganizationResolution(
        organization_id=organization_id,
        account_id=ACCOUNT_ID,
        phone_number_id="PHONE_NUMBER_123",
        whatsapp_business_account_id="WABA_123",
        provider_metadata={},
    )


def _identity(
    id: UUID = IDENTITY_ID,
    organization_id: UUID = ORGANIZATION_ID,
    customer_id: UUID = CUSTOMER_ID,
    provider_user_id: str = WA_ID,
) -> CustomerIdentityRead:
    return CustomerIdentityRead(
        id=id,
        organization_id=organization_id,
        customer_id=customer_id,
        provider="whatsapp",
        provider_user_id=provider_user_id,
        provider_username="Asha Buyer",
        provider_phone=None,
        metadata={},
    )


def _customer(
    id: UUID = CUSTOMER_ID,
    organization_id: UUID = ORGANIZATION_ID,
) -> CustomerRead:
    return CustomerRead(
        id=id,
        organization_id=organization_id,
        display_name="Asha Buyer",
        email=None,
        phone_number=None,
        status=CustomerStatus.LEAD,
        lead_stage=LeadStage.NEW,
        purchase_stage="unknown",
    )

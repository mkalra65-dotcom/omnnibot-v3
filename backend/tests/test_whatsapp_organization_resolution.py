from pathlib import Path
from uuid import UUID

import pytest

from app.db.models.common import WhatsAppAccountStatus
from app.db.models.records import WhatsAppAccountRead
from app.services.whatsapp_organization_resolution import (
    WhatsAppOrganizationResolutionError,
    WhatsAppOrganizationResolutionService,
)
from app.services.whatsapp_payloads import MetaWhatsAppPayloadError, parse_meta_whatsapp_webhook


FIXTURES_DIR = Path(__file__).parent / "fixtures"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
ACCOUNT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ACCOUNT_ID = UUID("44444444-4444-4444-4444-444444444444")


class FakeWhatsAppAccountRepository:
    def __init__(self, accounts: list[WhatsAppAccountRead]) -> None:
        self.accounts = accounts

    def list_active_by_phone_number_id(
        self,
        phone_number_id: str,
        limit: int = 2,
    ) -> list[WhatsAppAccountRead]:
        matches = [
            account
            for account in self.accounts
            if account.phone_number_id == phone_number_id
            and account.status == WhatsAppAccountStatus.ACTIVE
        ]
        return matches[:limit]


def test_parse_meta_payload_extracts_account_metadata() -> None:
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()

    payload = parse_meta_whatsapp_webhook(raw_body)

    assert payload.phone_number_id == "PHONE_NUMBER_123"
    assert payload.whatsapp_business_account_id == "WABA_123"
    assert payload.provider_metadata == {
        "provider": "whatsapp",
        "source": "meta",
        "object": "whatsapp_business_account",
        "fields": ["messages"],
        "messaging_products": ["whatsapp"],
        "display_phone_numbers": ["15551234567"],
    }


def test_parse_meta_payload_rejects_malformed_json() -> None:
    with pytest.raises(MetaWhatsAppPayloadError):
        parse_meta_whatsapp_webhook(b'{"object": "whatsapp_business_account"')


def test_parse_meta_payload_rejects_missing_phone_number_id() -> None:
    raw_body = b"""
    {
      "object": "whatsapp_business_account",
      "entry": [
        {
          "id": "WABA_123",
          "changes": [
            {
              "field": "messages",
              "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                  "display_phone_number": "15551234567"
                }
              }
            }
          ]
        }
      ]
    }
    """

    with pytest.raises(MetaWhatsAppPayloadError):
        parse_meta_whatsapp_webhook(raw_body)


def test_resolves_valid_active_account() -> None:
    payload = _payload()
    service = _service([_account()])

    resolution = service.resolve(payload)

    assert resolution.organization_id == ORGANIZATION_ID
    assert resolution.account_id == ACCOUNT_ID
    assert resolution.phone_number_id == "PHONE_NUMBER_123"
    assert resolution.whatsapp_business_account_id == "WABA_123"
    assert resolution.provider_metadata["provider"] == "whatsapp"


def test_fails_closed_for_missing_account() -> None:
    service = _service([])

    with pytest.raises(WhatsAppOrganizationResolutionError):
        service.resolve(_payload())


def test_fails_closed_for_disabled_account() -> None:
    service = _service([_account(status=WhatsAppAccountStatus.DISABLED)])

    with pytest.raises(WhatsAppOrganizationResolutionError):
        service.resolve(_payload())


def test_fails_closed_for_revoked_account() -> None:
    service = _service([_account(status=WhatsAppAccountStatus.REVOKED)])

    with pytest.raises(WhatsAppOrganizationResolutionError):
        service.resolve(_payload())


def test_fails_closed_for_duplicate_active_accounts() -> None:
    service = _service(
        [
            _account(),
            _account(id=OTHER_ACCOUNT_ID, organization_id=OTHER_ORGANIZATION_ID),
        ]
    )

    with pytest.raises(WhatsAppOrganizationResolutionError):
        service.resolve(_payload())


def _service(accounts: list[WhatsAppAccountRead]) -> WhatsAppOrganizationResolutionService:
    return WhatsAppOrganizationResolutionService(
        repository=FakeWhatsAppAccountRepository(accounts)
    )


def _payload():
    raw_body = (FIXTURES_DIR / "meta_whatsapp_text_message.json").read_bytes()
    return parse_meta_whatsapp_webhook(raw_body)


def _account(
    id: UUID = ACCOUNT_ID,
    organization_id: UUID = ORGANIZATION_ID,
    status: WhatsAppAccountStatus = WhatsAppAccountStatus.ACTIVE,
) -> WhatsAppAccountRead:
    return WhatsAppAccountRead(
        id=id,
        organization_id=organization_id,
        phone_number_id="PHONE_NUMBER_123",
        whatsapp_business_account_id="WABA_123",
        display_phone_number="15551234567",
        status=status,
        metadata={},
    )

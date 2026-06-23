from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.repositories.whatsapp_account_repository import WhatsAppAccountRepository
from app.services.whatsapp_payloads import MetaWhatsAppWebhookPayload


class WhatsAppOrganizationResolutionError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class WhatsAppOrganizationResolution:
    organization_id: UUID
    account_id: UUID
    phone_number_id: str
    whatsapp_business_account_id: str | None
    provider_metadata: dict


class WhatsAppOrganizationResolutionService:
    def __init__(
        self,
        repository: WhatsAppAccountRepository | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self._repository = repository
        self._supabase_factory = supabase_factory

    def resolve(
        self,
        payload: MetaWhatsAppWebhookPayload,
    ) -> WhatsAppOrganizationResolution:
        accounts = self.repository.list_active_by_phone_number_id(
            payload.phone_number_id,
            limit=2,
        )

        if len(accounts) != 1:
            raise WhatsAppOrganizationResolutionError("WhatsApp account did not resolve uniquely")

        account = accounts[0]
        return WhatsAppOrganizationResolution(
            organization_id=account.organization_id,
            account_id=account.id,
            phone_number_id=account.phone_number_id,
            whatsapp_business_account_id=account.whatsapp_business_account_id,
            provider_metadata=payload.provider_metadata,
        )

    @property
    def repository(self) -> WhatsAppAccountRepository:
        if self._repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._repository = WhatsAppAccountRepository(factory.get_service_client())
        return self._repository

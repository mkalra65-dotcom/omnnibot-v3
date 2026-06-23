from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import ChannelType, ConversationStatus, PaginationOptions
from app.db.models.queries import ConversationFilters
from app.db.models.records import ConversationCreate, ConversationRead
from app.db.repositories.conversation_repository import ConversationRepository
from app.services.whatsapp_customer_identity_resolution import WhatsAppCustomerIdentityResolution


class WhatsAppConversationResolutionError(LookupError):
    pass


class WhatsAppConversationInputError(WhatsAppConversationResolutionError):
    pass


@dataclass(frozen=True, slots=True)
class WhatsAppConversationResolution:
    organization_id: UUID
    customer_id: UUID
    channel: str
    conversation_id: UUID | None
    existing_conversation: bool
    conversation_creation_required: bool
    conversation_resolution_conflict: bool

    @classmethod
    def existing(
        cls,
        organization_id: UUID,
        customer_id: UUID,
        conversation: ConversationRead,
    ) -> WhatsAppConversationResolution:
        return cls(
            organization_id=organization_id,
            customer_id=customer_id,
            channel=ChannelType.WHATSAPP.value,
            conversation_id=conversation.id,
            existing_conversation=True,
            conversation_creation_required=False,
            conversation_resolution_conflict=False,
        )

    @classmethod
    def missing(
        cls,
        organization_id: UUID,
        customer_id: UUID,
    ) -> WhatsAppConversationResolution:
        return cls(
            organization_id=organization_id,
            customer_id=customer_id,
            channel=ChannelType.WHATSAPP.value,
            conversation_id=None,
            existing_conversation=False,
            conversation_creation_required=True,
            conversation_resolution_conflict=False,
        )

    @classmethod
    def conflict(
        cls,
        organization_id: UUID,
        customer_id: UUID,
    ) -> WhatsAppConversationResolution:
        return cls(
            organization_id=organization_id,
            customer_id=customer_id,
            channel=ChannelType.WHATSAPP.value,
            conversation_id=None,
            existing_conversation=False,
            conversation_creation_required=False,
            conversation_resolution_conflict=True,
        )

    def as_response(self) -> dict[str, str | bool | None]:
        return {
            "organization_id": str(self.organization_id),
            "customer_id": str(self.customer_id),
            "channel": self.channel,
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "existing_conversation": self.existing_conversation,
            "conversation_creation_required": self.conversation_creation_required,
            "conversation_resolution_conflict": self.conversation_resolution_conflict,
        }


class WhatsAppConversationResolutionService:
    def __init__(
        self,
        repository: ConversationRepository | None = None,
        supabase_factory: SupabaseClientFactory | None = None,
    ) -> None:
        self._repository = repository
        self._supabase_factory = supabase_factory

    def resolve(
        self,
        customer_identity_resolution: WhatsAppCustomerIdentityResolution,
    ) -> WhatsAppConversationResolution:
        organization_id = customer_identity_resolution.organization_id
        if organization_id is None:
            raise WhatsAppConversationInputError("organization_id is required")

        customer_id = customer_identity_resolution.customer_id
        if customer_id is None:
            raise WhatsAppConversationInputError("customer_id is required")

        conversations = self.repository.list_by_customer(
            organization_id=organization_id,
            customer_id=customer_id,
            filters=ConversationFilters(
                status=ConversationStatus.OPEN,
                channel=ChannelType.WHATSAPP,
            ),
            pagination=PaginationOptions(limit=2),
        ).items
        if not conversations:
            conversation = self.repository.create(
                organization_id,
                ConversationCreate(
                    customer_id=customer_id,
                    channel=ChannelType.WHATSAPP,
                    status=ConversationStatus.OPEN,
                    metadata={
                        "source": "whatsapp_webhook",
                        "provider": "whatsapp",
                    },
                ),
            )
            return WhatsAppConversationResolution.existing(
                organization_id=organization_id,
                customer_id=customer_id,
                conversation=conversation,
            )
        if len(conversations) > 1:
            return WhatsAppConversationResolution.conflict(
                organization_id=organization_id,
                customer_id=customer_id,
            )

        return WhatsAppConversationResolution.existing(
            organization_id=organization_id,
            customer_id=customer_id,
            conversation=conversations[0],
        )

    @property
    def repository(self) -> ConversationRepository:
        if self._repository is None:
            factory = self._supabase_factory or get_supabase_factory()
            self._repository = ConversationRepository(factory.get_service_client())
        return self._repository

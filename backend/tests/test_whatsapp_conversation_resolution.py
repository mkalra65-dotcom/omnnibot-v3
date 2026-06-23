from uuid import UUID

import pytest

from app.db.models.common import ChannelType, ConversationStatus, PaginationOptions, RepositoryPage
from app.db.models.queries import ConversationFilters
from app.db.models.records import ConversationCreate, ConversationRead
from app.services.whatsapp_conversation_resolution import (
    WhatsAppConversationInputError,
    WhatsAppConversationResolutionService,
)
from app.services.whatsapp_customer_identity_resolution import WhatsAppCustomerIdentityResolution


ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
CUSTOMER_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_CUSTOMER_ID = UUID("44444444-4444-4444-4444-444444444444")
CONVERSATION_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_CONVERSATION_ID = UUID("66666666-6666-6666-6666-666666666666")


class FakeConversationRepository:
    def __init__(self, conversations: list[ConversationRead] | None = None) -> None:
        self.conversations = conversations or []
        self.lookups: list[tuple[UUID, UUID, ConversationFilters | None, PaginationOptions | None]] = []
        self.created_payloads: list[ConversationCreate] = []

    def list_by_customer(
        self,
        organization_id: UUID,
        customer_id: UUID,
        filters: ConversationFilters | None = None,
        pagination: PaginationOptions | None = None,
        sort=None,
    ) -> RepositoryPage[ConversationRead]:
        self.lookups.append((organization_id, customer_id, filters, pagination))
        matches = [
            conversation
            for conversation in self.conversations
            if (
                conversation.organization_id == organization_id
                and conversation.customer_id == customer_id
                and (filters is None or filters.status is None or conversation.status == filters.status)
                and (filters is None or filters.channel is None or conversation.channel == filters.channel)
            )
        ]
        if pagination and pagination.limit is not None:
            matches = matches[: pagination.limit]
        return RepositoryPage(
            items=matches,
            total=len(matches),
            page=1,
            page_size=len(matches),
            offset=0,
            limit=pagination.limit if pagination and pagination.limit else len(matches),
        )

    def create(self, organization_id: UUID, payload: ConversationCreate) -> ConversationRead:
        self.created_payloads.append(payload)
        conversation = _conversation(
            id=OTHER_CONVERSATION_ID,
            organization_id=organization_id,
            customer_id=payload.customer_id,
            channel=payload.channel,
            status=payload.status,
        ).model_copy(update={"metadata": payload.metadata})
        self.conversations.append(conversation)
        return conversation


def test_resolves_existing_open_conversation() -> None:
    repository = FakeConversationRepository(conversations=[_conversation()])
    service = WhatsAppConversationResolutionService(repository=repository)

    resolution = service.resolve(_customer_identity_resolution())

    assert resolution.organization_id == ORGANIZATION_ID
    assert resolution.customer_id == CUSTOMER_ID
    assert resolution.channel == "whatsapp"
    assert resolution.conversation_id == CONVERSATION_ID
    assert resolution.existing_conversation is True
    assert resolution.conversation_creation_required is False
    assert resolution.conversation_resolution_conflict is False
    assert len(repository.lookups) == 1
    lookup_organization_id, lookup_customer_id, filters, pagination = repository.lookups[0]
    assert lookup_organization_id == ORGANIZATION_ID
    assert lookup_customer_id == CUSTOMER_ID
    assert filters == ConversationFilters(
        status=ConversationStatus.OPEN,
        channel=ChannelType.WHATSAPP,
    )
    assert pagination == PaginationOptions(limit=2)


def test_no_conversation_creates_open_whatsapp_conversation() -> None:
    repository = FakeConversationRepository()
    service = WhatsAppConversationResolutionService(repository=repository)

    resolution = service.resolve(_customer_identity_resolution())

    assert resolution.conversation_id == OTHER_CONVERSATION_ID
    assert resolution.existing_conversation is True
    assert resolution.conversation_creation_required is False
    assert resolution.conversation_resolution_conflict is False
    assert repository.created_payloads[0].customer_id == CUSTOMER_ID
    assert repository.created_payloads[0].channel == ChannelType.WHATSAPP
    assert repository.created_payloads[0].status == ConversationStatus.OPEN


def test_closed_conversation_is_not_reused() -> None:
    repository = FakeConversationRepository(
        conversations=[_conversation(status=ConversationStatus.CLOSED)]
    )
    service = WhatsAppConversationResolutionService(repository=repository)

    resolution = service.resolve(_customer_identity_resolution())

    assert resolution.conversation_id == OTHER_CONVERSATION_ID
    assert resolution.conversation_creation_required is False
    assert resolution.conversation_resolution_conflict is False


def test_same_customer_in_another_organization_does_not_resolve() -> None:
    repository = FakeConversationRepository(
        conversations=[
            _conversation(
                organization_id=OTHER_ORGANIZATION_ID,
                customer_id=CUSTOMER_ID,
                id=OTHER_CONVERSATION_ID,
            )
        ]
    )
    service = WhatsAppConversationResolutionService(repository=repository)

    resolution = service.resolve(_customer_identity_resolution())

    assert resolution.conversation_id == OTHER_CONVERSATION_ID
    assert resolution.conversation_creation_required is False
    assert len(repository.lookups) == 1
    lookup_organization_id, lookup_customer_id, filters, pagination = repository.lookups[0]
    assert lookup_organization_id == ORGANIZATION_ID
    assert lookup_customer_id == CUSTOMER_ID
    assert filters == ConversationFilters(
        status=ConversationStatus.OPEN,
        channel=ChannelType.WHATSAPP,
    )
    assert pagination == PaginationOptions(limit=2)


def test_duplicate_open_conversations_returns_conflict_without_selecting_conversation() -> None:
    repository = FakeConversationRepository(
        conversations=[
            _conversation(id=CONVERSATION_ID),
            _conversation(id=OTHER_CONVERSATION_ID),
        ]
    )
    service = WhatsAppConversationResolutionService(repository=repository)

    resolution = service.resolve(_customer_identity_resolution())

    assert resolution.conversation_id is None
    assert resolution.existing_conversation is False
    assert resolution.conversation_creation_required is False
    assert resolution.conversation_resolution_conflict is True


def test_rejects_missing_customer_id() -> None:
    service = WhatsAppConversationResolutionService(repository=FakeConversationRepository())

    with pytest.raises(WhatsAppConversationInputError):
        service.resolve(_customer_identity_resolution(customer_id=None))


def test_rejects_missing_organization_id() -> None:
    service = WhatsAppConversationResolutionService(repository=FakeConversationRepository())

    with pytest.raises(WhatsAppConversationInputError):
        service.resolve(
            _customer_identity_resolution(
                organization_id=None,  # type: ignore[arg-type]
            )
        )


def _customer_identity_resolution(
    organization_id: UUID = ORGANIZATION_ID,
    customer_id: UUID | None = CUSTOMER_ID,
) -> WhatsAppCustomerIdentityResolution:
    return WhatsAppCustomerIdentityResolution(
        organization_id=organization_id,
        provider="whatsapp",
        wa_id="919876543210",
        identity_id=None,
        customer_id=customer_id,
        customer_creation_required=customer_id is None,
    )


def _conversation(
    id: UUID = CONVERSATION_ID,
    organization_id: UUID = ORGANIZATION_ID,
    customer_id: UUID = CUSTOMER_ID,
    channel: ChannelType = ChannelType.WHATSAPP,
    status: ConversationStatus = ConversationStatus.OPEN,
) -> ConversationRead:
    return ConversationRead(
        id=id,
        organization_id=organization_id,
        customer_id=customer_id,
        channel=channel,
        status=status,
        handoff_status="ai",
        priority="normal",
    )

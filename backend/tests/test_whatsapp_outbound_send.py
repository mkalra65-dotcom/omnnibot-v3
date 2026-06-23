from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.db.models.common import (
    ChannelType,
    ConversationStatus,
    MessageStatus,
    PaginationOptions,
    RepositoryPage,
    WhatsAppAccountStatus,
)
from app.db.models.records import (
    AiDraftReviewRead,
    AiDraftReviewUpdate,
    ConversationRead,
    CustomerIdentityRead,
    MessageCreate,
    MessageRead,
    WhatsAppAccountRead,
)
from app.db.repositories.base_repository import OrganizationContext
from app.services.organization_access import TenantContext
from app.services.secrets import SecretResolutionError
from app.services.whatsapp_outbound_provider import (
    WhatsAppOutboundProviderError,
    WhatsAppOutboundProviderTimeout,
    WhatsAppOutboundSendResult,
)
from app.services.whatsapp_outbound_send import WhatsAppOutboundSendService


ORG_A = UUID("10000000-0000-0000-0000-000000000001")
ORG_B = UUID("20000000-0000-0000-0000-000000000001")
USER_ID = UUID("30000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("40000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("50000000-0000-0000-0000-000000000001")
CUSTOMER_ID = UUID("60000000-0000-0000-0000-000000000001")


def test_viewer_cannot_send() -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status="approved")

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("viewer"), review.id, send_idempotency_key="send-1")

    assert error.value.status_code == 403
    assert provider.requests == []


@pytest.mark.parametrize("role", ["agent", "manager", "admin", "owner"])
def test_agent_manager_admin_owner_can_send(role: str) -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status="approved")

    result = service.send_review(_tenant(role), review.id, send_idempotency_key=f"send-{role}")

    assert result.status == "sent"
    assert result.external_message_id == "wamid.outbound-1"
    assert len(provider.requests) == 1


@pytest.mark.parametrize("review_status", ["pending", "rejected"])
def test_unsendable_review_status_cannot_send(review_status: str) -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status=review_status)

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-1")

    assert error.value.status_code == 409
    assert provider.requests == []


def test_already_sent_review_does_not_double_send() -> None:
    service, repos, provider, _ = _service()
    message = repos.messages.seed(external_message_id="wamid.existing", status=MessageStatus.SENT)
    review = repos.reviews.seed(
        status="sent",
        sent_message_id=message.id,
        sent_at=datetime.now(timezone.utc),
        send_idempotency_key="send-existing",
    )

    result = service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-new")

    assert result.idempotent is True
    assert result.external_message_id == "wamid.existing"
    assert provider.requests == []


def test_approved_review_sends_draft_text_and_persists_outbound_message() -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status="approved", draft_text="Approved draft.")

    result = service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-approved")

    assert result.status == "sent"
    assert provider.requests[0].body == "Approved draft."
    message = repos.messages.records[result.message_id]
    assert message.direction == "outbound"
    assert message.channel == ChannelType.WHATSAPP
    assert message.sender_type == "human"
    assert message.sender_user_id == USER_ID
    assert message.sent_by_human is True
    assert message.generated_by_ai is False
    assert message.status == MessageStatus.SENT
    assert message.external_message_id == "wamid.outbound-1"
    assert message.sent_at is not None
    assert message.metadata["ai_assisted"] is True
    assert message.metadata["ai_draft_review_id"] == str(review.id)
    updated_review = repos.reviews.records[review.id]
    assert updated_review.status == "sent"
    assert updated_review.sent_message_id == message.id
    assert updated_review.sent_by_membership_id == MEMBERSHIP_ID
    assert updated_review.provider_response == {"messages": [{"id": "wamid.outbound-1"}]}
    assert repos.conversations.records[CONVERSATION_ID].last_message_id == message.id


def test_edited_review_sends_edited_text() -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status="edited", draft_text="Draft text.", edited_text="Edited text.")

    service.send_review(_tenant("manager"), review.id, send_idempotency_key="send-edited")

    assert provider.requests[0].body == "Edited text."


def test_cross_organization_blocked() -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(organization_id=ORG_B, status="approved")

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("owner", organization_id=ORG_A), review.id, send_idempotency_key="send-1")

    assert error.value.status_code == 404
    assert provider.requests == []


def test_missing_active_whatsapp_account_fails_safely() -> None:
    service, repos, provider, _ = _service(active_accounts=[])
    review = repos.reviews.seed(status="approved")

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-1")

    assert error.value.status_code == 424
    assert provider.requests == []
    assert repos.messages.records == {}


def test_missing_token_fails_safely() -> None:
    service, repos, provider, _ = _service(secret_value=None)
    review = repos.reviews.seed(status="approved")

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-1")

    assert error.value.status_code == 424
    assert provider.requests == []
    message = next(iter(repos.messages.records.values()))
    assert message.status == MessageStatus.FAILED
    updated_review = repos.reviews.records[review.id]
    assert updated_review.status == "approved"
    assert updated_review.send_error_code == "missing_whatsapp_access_token"


def test_meta_failure_records_error_and_does_not_mark_sent() -> None:
    service, repos, provider, _ = _service(provider_mode="failure")
    review = repos.reviews.seed(status="approved")

    with pytest.raises(HTTPException) as error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-failure")

    assert error.value.status_code == 502
    message = next(iter(repos.messages.records.values()))
    assert message.status == MessageStatus.FAILED
    updated_review = repos.reviews.records[review.id]
    assert updated_review.status == "approved"
    assert updated_review.send_error_code == "meta_api_error"
    assert updated_review.sent_at is None


def test_meta_timeout_unknown_outcome_does_not_blindly_retry() -> None:
    service, repos, provider, _ = _service(provider_mode="timeout")
    review = repos.reviews.seed(status="approved")

    with pytest.raises(HTTPException) as first_error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-timeout")
    with pytest.raises(HTTPException) as retry_error:
        service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-timeout")

    assert first_error.value.status_code == 504
    assert retry_error.value.status_code == 409
    assert len(provider.requests) == 1
    message = next(iter(repos.messages.records.values()))
    assert message.status == MessageStatus.QUEUED
    assert repos.reviews.records[review.id].send_error_code == "meta_timeout"


def test_duplicate_idempotency_key_returns_existing_sent_result() -> None:
    service, repos, provider, _ = _service()
    review = repos.reviews.seed(status="approved")

    first = service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-same")
    second = service.send_review(_tenant("agent"), review.id, send_idempotency_key="send-same")

    assert first.external_message_id == "wamid.outbound-1"
    assert second.external_message_id == "wamid.outbound-1"
    assert second.idempotent is True
    assert len(provider.requests) == 1


def test_no_auto_send_path_exists() -> None:
    from app.services.ai_draft_review import AIDraftReviewService

    assert not hasattr(AIDraftReviewService, "send_review")


class FakeRepos:
    def __init__(self, active_accounts: list[WhatsAppAccountRead] | None) -> None:
        self.reviews = FakeReviewRepository()
        self.messages = FakeMessageRepository()
        self.conversations = FakeConversationRepository()
        self.customers = FakeCustomerRepository()
        self.accounts = FakeWhatsAppAccountRepository(active_accounts)


class FakeReviewRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, AiDraftReviewRead] = {}

    def seed(
        self,
        *,
        organization_id: UUID = ORG_A,
        status: str = "approved",
        draft_text: str = "Draft reply.",
        edited_text: str | None = None,
        sent_message_id: UUID | None = None,
        sent_at: datetime | None = None,
        send_idempotency_key: str | None = None,
    ) -> AiDraftReviewRead:
        review = _review(
            organization_id=organization_id,
            status=status,
            draft_text=draft_text,
            edited_text=edited_text,
            sent_message_id=sent_message_id,
            sent_at=sent_at,
            send_idempotency_key=send_idempotency_key,
        )
        self.records[review.id] = review
        return review

    def get_by_id(self, organization_id, record_id):
        record = self.records.get(record_id)
        return record if record and record.organization_id == _org_id(organization_id) else None

    def get_by_send_idempotency_key(self, organization_id, send_idempotency_key):
        org_id = _org_id(organization_id)
        for record in self.records.values():
            if record.organization_id == org_id and record.send_idempotency_key == send_idempotency_key:
                return record
        return None

    def claim_for_send(self, organization_id, review_id, send_idempotency_key):
        record = self.get_by_id(organization_id, review_id)
        if record is None or record.status not in {"approved", "edited"} or record.send_idempotency_key:
            return None
        updated = record.model_copy(update={"send_idempotency_key": send_idempotency_key})
        self.records[review_id] = updated
        return updated

    def update(self, organization_id, record_id, payload):
        record = self.get_by_id(organization_id, record_id)
        if record is None:
            return None
        data = _payload_data(payload)
        updated = record.model_copy(update=data)
        self.records[record_id] = updated
        return updated


class FakeMessageRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, MessageRead] = {}

    def seed(
        self,
        *,
        external_message_id: str | None = None,
        status: MessageStatus = MessageStatus.QUEUED,
    ) -> MessageRead:
        message = _message(external_message_id=external_message_id, status=status)
        self.records[message.id] = message
        return message

    def create(self, organization_id, payload: MessageCreate):
        message = _message(
            organization_id=_org_id(organization_id),
            conversation_id=payload.conversation_id,
            customer_id=payload.customer_id,
            channel=payload.channel,
            direction=payload.direction,
            sender_type=payload.sender_type,
            sender_user_id=payload.sender_user_id,
            body=payload.body,
            status=payload.status,
            generated_by_ai=payload.generated_by_ai,
            sent_by_human=payload.sent_by_human,
            metadata=payload.metadata,
        )
        self.records[message.id] = message
        return message

    def get_by_id(self, organization_id, record_id):
        record = self.records.get(record_id)
        return record if record and record.organization_id == _org_id(organization_id) else None

    def update(self, organization_id, record_id, payload):
        record = self.get_by_id(organization_id, record_id)
        if record is None:
            return None
        data = _payload_data(payload)
        updated = record.model_copy(update=data)
        self.records[record_id] = updated
        return updated


class FakeConversationRepository:
    def __init__(self) -> None:
        self.records = {CONVERSATION_ID: _conversation()}

    def get_by_id(self, organization_id, record_id):
        record = self.records.get(record_id)
        return record if record and record.organization_id == _org_id(organization_id) else None

    def update_last_message(self, organization_id, conversation_id, last_message_id, last_message_at):
        record = self.get_by_id(organization_id, conversation_id)
        updated = record.model_copy(update={"last_message_id": last_message_id, "last_message_at": last_message_at})
        self.records[conversation_id] = updated
        return updated


class FakeCustomerRepository:
    def list_identities_for_customer(self, organization_id, customer_id):
        return [
            CustomerIdentityRead(
                id=uuid4(),
                organization_id=_org_id(organization_id),
                customer_id=customer_id,
                provider="whatsapp",
                provider_user_id="919999999999",
                created_at=datetime.now(timezone.utc),
            )
        ]


class FakeWhatsAppAccountRepository:
    def __init__(self, active_accounts: list[WhatsAppAccountRead] | None) -> None:
        self.active_accounts = [_account()] if active_accounts is None else active_accounts

    def list_by_organization(self, organization_id, filters=None, pagination=None, sort=None):
        org_id = _org_id(organization_id)
        items = [account for account in self.active_accounts if account.organization_id == org_id]
        options = pagination or PaginationOptions()
        return RepositoryPage(
            items=items,
            total=len(items),
            page=options.page or 1,
            page_size=options.page_size or len(items) or 1,
            offset=0,
            limit=options.page_size or len(items) or 1,
        )


class FakeOrganizationAccessService:
    def require_role(self, user_id, organization_id, allowed_roles):
        role = _ROLES[(user_id, organization_id)]
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="User role is not allowed")


class FakeSecretResolver:
    def __init__(self, value: str | None) -> None:
        self.value = value
        self.resolved_refs: list[str] = []

    def resolve(self, secret_ref: str) -> str:
        self.resolved_refs.append(secret_ref)
        if self.value is None:
            raise SecretResolutionError("missing")
        return self.value


class FakeProvider:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.requests = []

    def send_text(self, payload):
        self.requests.append(payload)
        if self.mode == "failure":
            raise WhatsAppOutboundProviderError("meta_api_error", "Meta rejected message")
        if self.mode == "timeout":
            raise WhatsAppOutboundProviderTimeout("meta_timeout", "Meta timed out")
        return WhatsAppOutboundSendResult(
            external_message_id="wamid.outbound-1",
            provider_response={"messages": [{"id": "wamid.outbound-1"}]},
        )


_ROLES: dict[tuple[UUID, UUID], str] = {}


def _service(
    *,
    active_accounts: list[WhatsAppAccountRead] | None = None,
    secret_value: str | None = "secret-token",
    provider_mode: str = "success",
):
    repos = FakeRepos(active_accounts)
    provider = FakeProvider(provider_mode)
    secret_resolver = FakeSecretResolver(secret_value)
    service = WhatsAppOutboundSendService(
        review_repository=repos.reviews,
        message_repository=repos.messages,
        conversation_repository=repos.conversations,
        customer_repository=repos.customers,
        whatsapp_account_repository=repos.accounts,
        organization_access_service=FakeOrganizationAccessService(),
        secret_resolver=secret_resolver,
        provider=provider,
        supabase_factory=None,
    )
    return service, repos, provider, secret_resolver


def _tenant(role: str, *, organization_id: UUID = ORG_A) -> TenantContext:
    _ROLES[(USER_ID, organization_id)] = role
    return TenantContext(
        organization_id=organization_id,
        user_id=USER_ID,
        membership_id=MEMBERSHIP_ID,
        role=role,
    )


def _review(
    *,
    organization_id: UUID = ORG_A,
    status: str = "approved",
    draft_text: str = "Draft reply.",
    edited_text: str | None = None,
    sent_message_id: UUID | None = None,
    sent_at: datetime | None = None,
    send_idempotency_key: str | None = None,
) -> AiDraftReviewRead:
    return AiDraftReviewRead(
        id=uuid4(),
        organization_id=organization_id,
        conversation_id=CONVERSATION_ID,
        customer_id=CUSTOMER_ID,
        draft_text=draft_text,
        edited_text=edited_text,
        status=status,
        approved_by_membership_id=MEMBERSHIP_ID,
        approved_at=datetime.now(timezone.utc),
        sent_message_id=sent_message_id,
        sent_at=sent_at,
        send_idempotency_key=send_idempotency_key,
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _message(
    *,
    organization_id: UUID = ORG_A,
    conversation_id: UUID = CONVERSATION_ID,
    customer_id: UUID | None = CUSTOMER_ID,
    channel: ChannelType = ChannelType.WHATSAPP,
    direction: str = "outbound",
    sender_type: str = "human",
    sender_user_id: UUID | None = USER_ID,
    external_message_id: str | None = None,
    body: str | None = "Message body",
    status: MessageStatus = MessageStatus.QUEUED,
    generated_by_ai: bool = False,
    sent_by_human: bool = True,
    metadata: dict[str, Any] | None = None,
) -> MessageRead:
    return MessageRead(
        id=uuid4(),
        organization_id=organization_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        channel=channel,
        direction=direction,
        sender_type=sender_type,
        sender_user_id=sender_user_id,
        external_message_id=external_message_id,
        message_type="text",
        body=body,
        status=status,
        generated_by_ai=generated_by_ai,
        sent_by_human=sent_by_human,
        metadata=metadata or {},
        provider_payload={},
        sent_at=datetime.now(timezone.utc) if status == MessageStatus.SENT else None,
        created_at=datetime.now(timezone.utc),
    )


def _conversation() -> ConversationRead:
    return ConversationRead(
        id=CONVERSATION_ID,
        organization_id=ORG_A,
        customer_id=CUSTOMER_ID,
        channel=ChannelType.WHATSAPP,
        status=ConversationStatus.OPEN,
        handoff_status="human_active",
        priority="normal",
        created_at=datetime.now(timezone.utc),
    )


def _account() -> WhatsAppAccountRead:
    return WhatsAppAccountRead(
        id=uuid4(),
        organization_id=ORG_A,
        phone_number_id="1234567890",
        whatsapp_business_account_id="waba-1",
        status=WhatsAppAccountStatus.ACTIVE,
        access_token_secret_ref="env:META_TOKEN",
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def _org_id(value) -> UUID:
    if isinstance(value, OrganizationContext):
        return value.organization_id
    return value


def _payload_data(payload) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="python", exclude_unset=True)
    return dict(payload)

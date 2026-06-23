# WhatsApp Ingestion Spec

This document specifies Phase 5A WhatsApp ingestion for OmniBot V3. It is documentation only. It does not implement WhatsApp code, migrations, backend application code, frontend code, Supabase configuration, `.env` changes, or secrets.

## Phase 5A Scope

Phase 5A adds planning for inbound WhatsApp webhook ingestion and persistence.

In scope:

- Webhook verification GET flow.
- Inbound webhook POST flow.
- Mocked Meta WhatsApp payload handling.
- Account-to-organization resolution.
- Customer identity resolution through `customer_identities`.
- Conversation create/reuse rules.
- Message persistence rules.
- Idempotency design.
- Retry, failure handling, tests, and acceptance criteria.

Out of scope:

- AI replies.
- Outbound WhatsApp sending.
- Media download.
- Meta OAuth or embedded signup.
- Production Meta app configuration.
- Supabase migrations in this documentation task.
- Frontend connection UI.

## Explicit Phase 5A Non-Goals

- No AI-generated replies.
- No outbound WhatsApp messages.
- No media download except safe metadata capture.
- No live Meta credentials required for tests.
- No changes to existing CRM/auth behavior.

## Future Files And Modules Likely Needed

Likely backend files:

- `backend/app/api/v1/routes/whatsapp_webhooks.py`
- `backend/app/schemas/whatsapp.py`
- `backend/app/services/whatsapp_ingestion.py`
- `backend/app/services/whatsapp_signature.py`
- `backend/app/services/customer_identity_resolution.py`
- `backend/app/repositories/customer_identities.py`
- `backend/app/repositories/conversations.py`
- `backend/app/repositories/messages.py`
- `backend/app/repositories/whatsapp_accounts.py`
- `backend/app/repositories/webhook_events.py`
- `backend/app/core/config.py`
- `backend/app/api/v1/router.py`

Likely tests:

- `backend/tests/test_whatsapp_webhook_verification.py`
- `backend/tests/test_whatsapp_ingestion.py`
- `backend/tests/fixtures/meta_whatsapp_text_message.json`
- `backend/tests/fixtures/meta_whatsapp_duplicate_delivery.json`
- `backend/tests/fixtures/meta_whatsapp_unsupported_media.json`

Likely future migrations, when implementation is approved:

- Add WhatsApp account mapping table, likely `whatsapp_accounts` or generic `organization_integrations`.
- Add webhook event/idempotency table, likely `webhook_events`.
- Add unique constraints for WhatsApp `external_message_id` scoped to provider and organization if not already sufficient.
- Add audit table before sensitive account mapping changes.

## Webhook Verification GET Flow

Endpoint target:

```text
GET /api/v1/webhooks/whatsapp
```

Expected query parameters:

- `hub.mode`
- `hub.verify_token`
- `hub.challenge`

Flow:

1. Parse query parameters.
2. Confirm `hub.mode == "subscribe"`.
3. Compare `hub.verify_token` with the server-side WhatsApp verify token.
4. If valid, return `hub.challenge` as plain text with 200.
5. If invalid, return 403.
6. Do not log the verify token.

The verify token must be stored as a server-side secret, not in source code or frontend code.

## Inbound POST Flow

Endpoint target:

```text
POST /api/v1/webhooks/whatsapp
```

High-level flow:

1. Receive JSON payload from Meta.
2. Verify request signature when available.
3. Parse `entry[]`, `changes[]`, and `value`.
4. Extract WhatsApp account identifiers such as `phone_number_id` and `whatsapp_business_account_id`.
5. Resolve exactly one organization from the account mapping.
6. Extract supported inbound messages.
7. Build idempotency keys from `external_message_id` and webhook delivery context.
8. Resolve or create a customer through `customer_identities`.
9. Reuse or create a WhatsApp conversation for the customer.
10. Persist inbound message rows with provider metadata.
11. Return 200 after safe persistence or duplicate detection.

Phase 5A should ignore or safely record unsupported events without sending replies.

## Mocked Meta Payload Examples

### Text Message

```json
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
              "display_phone_number": "15551234567",
              "phone_number_id": "PHONE_NUMBER_123"
            },
            "contacts": [
              {
                "profile": { "name": "Asha Buyer" },
                "wa_id": "919876543210"
              }
            ],
            "messages": [
              {
                "from": "919876543210",
                "id": "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA=",
                "timestamp": "1782144000",
                "type": "text",
                "text": {
                  "body": "Hi, is the blue kurti available in M?"
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### Unsupported Media Metadata

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "WABA_123",
      "changes": [
        {
          "field": "messages",
          "value": {
            "metadata": {
              "display_phone_number": "15551234567",
              "phone_number_id": "PHONE_NUMBER_123"
            },
            "contacts": [
              {
                "profile": { "name": "Asha Buyer" },
                "wa_id": "919876543210"
              }
            ],
            "messages": [
              {
                "from": "919876543210",
                "id": "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9JTUFHRQA=",
                "timestamp": "1782144060",
                "type": "image",
                "image": {
                  "id": "MEDIA_123",
                  "mime_type": "image/jpeg",
                  "sha256": "mocked-sha256"
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### Status Event To Ignore In Phase 5A

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "WABA_123",
      "changes": [
        {
          "field": "messages",
          "value": {
            "metadata": {
              "phone_number_id": "PHONE_NUMBER_123"
            },
            "statuses": [
              {
                "id": "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhggRkFLRV9NU0dfMQA=",
                "status": "delivered",
                "timestamp": "1782144100",
                "recipient_id": "919876543210"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

## Account-To-Organization Mapping

Phase 5A implementation will need a durable mapping from Meta WhatsApp identifiers to `organizations.id`.

Minimum mapping fields:

- `id`
- `organization_id`
- `provider`
- `whatsapp_business_account_id`
- `phone_number_id`
- `display_phone_number`
- `status`
- `metadata`
- `created_at`
- `updated_at`

Rules:

- `phone_number_id` should map to one active organization.
- `whatsapp_business_account_id` may map to multiple phone numbers over time, but each active phone number must be unambiguous.
- Webhook ingestion must fail closed if the account mapping is missing, inactive, duplicated, or ambiguous.
- Mapping connect, disconnect, and reassignment workflows should require owner/admin authorization and audit logging.

## Customer Identity Resolution

Customer identity resolution must use `customer_identities`.

For inbound WhatsApp messages:

1. Resolve `organization_id` from the WhatsApp account mapping.
2. Extract `wa_id` from `contacts[]` when present.
3. Extract sender phone from `messages[].from`.
4. Look up `customer_identities` by `organization_id`, `provider = "whatsapp"`, and provider identity fields.
5. If one identity exists, use its `customer_id`.
6. If no identity exists, create a `customers` row and a linked `customer_identities` row.
7. If multiple identities match, stop processing that message, record failure, and require manual remediation.

Recommended identity fields:

- `provider = "whatsapp"`
- `provider_user_id = contacts[].wa_id` or `messages[].from` when `wa_id` is unavailable.
- `provider_phone = messages[].from`
- `provider_username = contacts[].profile.name` only as display metadata, not a unique key.

Never resolve customers across organizations.

## Conversation Create/Reuse Rules

Conversation lookup must be organization-scoped.

Reuse an existing conversation when:

- `organization_id` matches.
- `customer_id` matches.
- `channel = "whatsapp"` or equivalent existing channel value.
- Conversation status is open or active.
- Handoff state does not require a separate thread.

Create a new conversation when:

- No open WhatsApp conversation exists for that organization/customer pair.
- The previous conversation is closed or archived.
- Future business rules decide to split conversations after a configurable inactivity window.

On inbound message persistence:

- Update `conversations.last_message_at` or equivalent existing timestamp if present.
- Update `conversations.last_customer_response_at` when available.
- Preserve handoff status; inbound ingestion must not auto-resolve handoff.
- Do not trigger AI replies in Phase 5A.

## Message Persistence Rules

Persist one inbound `messages` row per supported inbound WhatsApp message.

Required values:

- `organization_id`
- `customer_id`
- `conversation_id`
- `direction = "inbound"`
- `sender_type = "customer"`
- `channel = "whatsapp"` if the schema includes channel on messages or conversation context.
- `message_type`, such as `text`, `image`, or `unsupported`.
- `body` for text messages.
- `external_message_id` from Meta `messages[].id`.
- Provider timestamp converted to a database timestamp.
- Safe provider metadata needed for debugging and future reconciliation.

For media in Phase 5A:

- Do not download media files.
- Store only metadata such as media ID, mime type, hash, caption, and provider payload reference where safe.
- Mark media content as unsupported or metadata-only until media ingestion is approved.

For status events:

- Phase 5A may ignore delivery statuses or record them as unsupported webhook events.
- Do not create inbound customer messages from status-only events.

## Idempotency

Idempotency must prevent duplicate messages from Meta retries and internal retries.

Recommended keys:

- `external_message_id`: Meta `messages[].id`.
- `webhook_delivery_id`: request-level or derived event ID when available from headers or deterministic payload context.

Rules:

- Message persistence should be unique by organization, provider, and `external_message_id`.
- Webhook event persistence, if added, should be unique by provider and `webhook_delivery_id`.
- Duplicate POSTs should return 200 after confirming the existing persisted result.
- If a duplicate webhook contains conflicting payload data for the same external message ID, keep the original message immutable and record the conflict for audit/debugging.

If Meta does not provide a direct delivery ID in all environments, derive a deterministic fallback from provider, account ID, change index, message ID, and payload timestamp.

## Retry Strategy

Meta may retry webhook delivery when the endpoint fails or times out.

Handler strategy:

- Return 200 for successfully persisted messages.
- Return 200 for confirmed duplicates.
- Return 400 for malformed payloads that cannot be parsed.
- Return 403 for invalid signatures.
- Return 404 or 422 for unmapped provider accounts, depending on API convention.
- Return 500 only for transient internal failures where retry may succeed.

Internal strategy:

- Keep webhook handling fast.
- If future processing grows, persist the raw event and enqueue processing.
- Make queued processing idempotent by message and webhook event IDs.
- Use bounded retries with dead-letter visibility for repeated failures.

## Failure Handling

Failure cases and expected behavior:

- Invalid signature: reject and do not persist.
- Invalid JSON: reject and do not persist.
- Missing account identifiers: reject or record unresolved event without organization-owned writes.
- Unmapped account: reject or record platform-level unresolved event.
- Ambiguous account mapping: reject and alert operators.
- Missing customer identity: create customer and identity if enough sender data exists.
- Ambiguous customer identity: do not guess; record failure for manual remediation.
- Unsupported message type: persist metadata only or record unsupported event; do not download content.
- Duplicate message: return success without creating a duplicate.
- Database failure: return retryable error and rely on idempotency for later retry.

No failure path should send an outbound WhatsApp message in Phase 5A.

## Testing Strategy

Tests should use mocked payloads and require no live Meta credentials.

Recommended tests:

- GET verification succeeds with correct mode, token, and challenge.
- GET verification rejects invalid token.
- POST rejects invalid signature when signature verification is enabled.
- POST text payload resolves account mapping to organization.
- POST creates customer and `customer_identities` row for a new WhatsApp sender.
- POST reuses existing customer identity.
- POST creates or reuses the correct organization-scoped conversation.
- POST persists exactly one inbound message for a text payload.
- Duplicate POST does not create duplicate messages.
- Unsupported media stores metadata only and does not download media.
- Status-only payload does not create an inbound customer message.
- Unmapped account fails closed.
- Cross-organization identity collision does not leak or merge data.

Regression checks:

- Existing auth signup/login still works.
- Organization provisioning still works.
- Customer, conversation, and message CRUD still works.

## Acceptance Criteria

Phase 5A implementation will be acceptable when:

- Webhook GET verification is implemented and tested.
- Inbound POST accepts mocked Meta text payloads.
- Organization is resolved from WhatsApp account mapping, not from request headers.
- New WhatsApp senders create one customer and one `customer_identities` row.
- Existing WhatsApp identities reuse the correct customer within the same organization.
- Conversations are reused or created according to documented rules.
- Text messages are persisted as inbound customer messages.
- Duplicate webhook deliveries do not duplicate messages.
- Media payloads do not trigger downloads.
- No AI reply is generated.
- No outbound WhatsApp send occurs.
- All organization-scoped writes include `organization_id`.
- Tests pass without live Meta credentials.
- `git status` is clean after implementation commit.

## Implementation Recommendations

- Implement the webhook route as a thin controller and put parsing/resolution/persistence in a service.
- Keep Meta payload parsing isolated from database writes so mocked fixtures are easy to test.
- Add a small typed internal DTO for normalized inbound WhatsApp messages.
- Use repositories for account mapping, customer identities, conversations, messages, and webhook events.
- Prefer one service method such as `ingest_whatsapp_webhook(payload, headers)` that returns a structured result.
- Enforce idempotency at the database constraint level when migrations are approved.
- Add audit/event logging before production account reconnect or reassignment workflows.
- Keep Phase 5A synchronous only while it is lightweight; move to durable queued processing before media, AI, or high-volume accounts.

## Open Architectural Questions

- Should account mappings use a WhatsApp-specific `whatsapp_accounts` table or a generic `organization_integrations` table?
- Should webhook event logging be platform-level, organization-scoped after resolution, or split into both?
- Which exact enum values already exist for conversation channel, message direction, sender type, and message type?
- Should a closed conversation be reopened by a new inbound message or should a new conversation be created?
- What inactivity window should split WhatsApp conversations?
- What request header or deterministic fallback should define `webhook_delivery_id` for Meta deliveries?
- How long should raw provider payloads be retained?
- Which production component will enforce webhook rate limits?
- Which roles can connect or disconnect WhatsApp accounts?

## Future Roadmap

### Phase 5B: AI Drafting Or Controlled Replies

- Add organization-level AI enablement.
- Add subscription and quota checks before model calls.
- Add prompt-injection tests.
- Generate internal AI drafts or strictly controlled replies.
- Respect human handoff and conversation state.
- Record AI usage in `ai_interactions` and `organization_usage_daily`.

### Phase 5C: Outbound WhatsApp Sending

- Add outbound send service for Meta WhatsApp Cloud API.
- Add provider token storage and rotation.
- Add template-message support where required.
- Persist outbound messages before or after provider send according to final delivery semantics.
- Handle delivery statuses and provider errors.
- Add dashboard controls for human agents.

### Later Phases

- Media download and safe storage.
- Embedded signup or Meta OAuth onboarding.
- Instagram ingestion.
- RAG-backed product and FAQ answers.
- Advanced automation, followups, and campaign workflows.


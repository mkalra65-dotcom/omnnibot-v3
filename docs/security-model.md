# Security Model

This document defines the target security model for OmniBot V3 as Phase 5 begins. It is documentation only. It does not implement WhatsApp code, migrations, application code, Supabase configuration, or secrets.

## Security Principles

- `organization_id` is the hard data boundary for OmniBot V3.
- Authentication is not authorization. Access to organization data requires an active membership.
- `X-Organization-ID` is an untrusted context selector until the backend verifies membership.
- Service-role credentials may bypass database RLS, so every service-role path must enforce organization resolution in application code.
- External provider identifiers are untrusted input until verified, mapped, normalized, and scoped to one organization.
- AI and RAG features must never cross organization boundaries.

## Organization Isolation

All business-owned records must be scoped by `organization_id`, including customers, customer identities, conversations, messages, products, FAQ entries, AI logs, usage records, future integration mappings, future knowledge chunks, and future audit events.

Repository and service rules:

- Every organization-scoped read must include `organization_id`.
- Every organization-scoped write must write exactly one `organization_id`.
- Reads by child ID, such as `customer_id`, `conversation_id`, or `message_id`, must also include `organization_id`.
- Composite organization-safe relationships should be preferred where schema supports them.
- Background jobs and webhooks must resolve an organization before touching customer, conversation, message, AI, usage, or audit records.

## Membership Verification

Dashboard API requests must verify:

- The user is authenticated through Supabase Auth.
- The requested `organization_id` exists.
- The authenticated user has an active membership for that organization.
- The membership role allows the requested action.

Recommended role boundaries:

- `owner`: full organization control, billing, membership management, integration management, deletion/export approvals.
- `admin`: operational management except ownership transfer and destructive billing actions.
- `manager`: catalog, FAQ, conversation operations, and team workflow management.
- `agent`: customer and conversation operations, human handoff, and message handling.
- `viewer`: read-only access to allowed dashboards and reports.

Membership checks should run before repository calls. Repositories should not infer authorization from authentication alone.

## X-Organization-ID Validation

`X-Organization-ID` identifies the requested organization context for dashboard routes. It is not proof of access.

Validation requirements:

- Require the header on organization-scoped dashboard routes.
- Parse it as a UUID before use.
- Reject missing, malformed, or ambiguous organization context with a clear 400 or 422 response.
- Verify active membership before any organization-scoped read or write.
- Return 403 for authenticated users without access to the requested organization.
- Avoid falling back to a user's first organization implicitly on mutation routes.

Webhook routes should not trust or require `X-Organization-ID`; they should resolve the organization from verified provider account mappings.

## Service-Role Boundaries

Service-role database access is required for trusted backend operations such as onboarding, webhook ingestion, delivery-status updates, AI analysis, usage rollups, subscription updates, identity merges, audit logging, and retention workflows.

Service-role rules:

- Never expose service-role keys to browser clients.
- Store service-role secrets only in server-side runtime secret management.
- Keep service-role usage inside backend services, workers, or database administration workflows.
- Require explicit organization resolution before service-role writes.
- Log sensitive service-role mutations with actor, component, organization, table, record ID, request ID, and timestamp.
- Prefer narrow service methods over generic service-role write helpers.

## Customer Identity Resolution Security

Customer identity resolution must use `customer_identities`, not provider-specific columns on `customers`.

Resolution rules:

- Scope lookups by both `organization_id` and provider identity fields.
- Treat provider IDs, phone numbers, usernames, and profile names as untrusted external data.
- Normalize phone numbers and provider IDs before lookup when a reliable normalization rule exists.
- Do not merge customers across organizations.
- Do not merge identities only by display name.
- Require audited service-role workflows for manual merges, identity reassignment, or identity deletion.
- Preserve raw provider metadata only when needed for debugging, idempotency, or future reconciliation.

For WhatsApp, the safest initial identity key is:

- `provider = "whatsapp"`
- `provider_user_id = contacts[].wa_id` when present
- `provider_phone` derived from the same WhatsApp identity when safe
- `organization_id` from the verified WhatsApp account mapping

## Prompt Injection Protection

Future AI features must treat customer messages, merchant-uploaded content, product descriptions, FAQ text, provider metadata, and retrieved knowledge chunks as untrusted content.

Required controls before AI replies are enabled:

- Separate system/developer instructions from user and retrieved content.
- Never let customer-provided text override business policy, safety policy, tool permissions, organization scope, or handoff rules.
- Add prompt-injection test cases for messages that request secrets, cross-organization data, policy changes, hidden prompts, or tool misuse.
- Do not include secrets, raw tokens, service-role keys, database URLs, or internal config in prompts.
- Log AI decisions, model, usage, and safety outcomes in `ai_interactions` or a successor ledger.
- Require human handoff for high-risk requests such as payment disputes, legal threats, abuse, or identity/account changes.

## RAG Filtering By Organization

Future RAG retrieval must use `organization_id` as a hard pre-filter before ranking, reranking, or returning chunks to a model.

RAG requirements:

- Knowledge sources, chunks, embeddings, retrieval logs, and derived artifacts must carry `organization_id`.
- Vector queries must filter by `organization_id` at the database/query layer.
- Shared platform knowledge, if added, must be modeled separately and explicitly allowed.
- Retrieved chunks must include source IDs for auditability.
- RAG results must not be cached globally unless the cache key includes `organization_id` and all authorization-relevant inputs.

## WhatsApp Webhook Verification Security

Webhook verification and ingestion must follow Meta WhatsApp Cloud API expectations.

GET verification requirements:

- Compare `hub.verify_token` with a server-side secret.
- Return `hub.challenge` only when mode and token are valid.
- Do not log the verify token.
- Use HTTPS in deployed environments.

POST ingestion requirements:

- Verify Meta request signatures before trusting payloads when signature headers are available.
- Parse payloads defensively and reject malformed JSON.
- Resolve exactly one organization from verified Meta account identifiers such as `phone_number_id` or `whatsapp_business_account_id`.
- Process only supported event types in Phase 5A.
- Return quickly after safe persistence or duplicate detection.
- Avoid downloading media in Phase 5A; store metadata only.

## Meta Account Mapping Security

Meta account mappings connect external WhatsApp assets to an internal organization. A future schema should model this explicitly, likely as `whatsapp_accounts` or `organization_integrations`.

Mapping requirements:

- Each active `phone_number_id` should map to exactly one organization.
- Store `whatsapp_business_account_id`, `phone_number_id`, display phone number, connection status, and metadata.
- Protect tokens and app secrets with server-side secret management or encrypted storage.
- Do not expose provider access tokens in API responses.
- Require owner/admin authorization for connect, disconnect, reconnect, and token rotation workflows.
- Audit all mapping changes.
- Prevent accidental reassignment of a Meta asset without explicit admin action and audit trail.

## AI Usage Quotas

AI usage must be controlled per organization.

Quota checks should consider:

- Subscription plan and feature entitlements.
- Monthly AI request limit.
- Monthly token limit.
- Estimated cost limit.
- Trial or grace-period rules.
- Abuse or suspension status.

Before AI replies are enabled, the system should check quota before model calls and record usage after calls. Failed or blocked calls should still be observable for support and abuse analysis.

## Abuse Prevention

Abuse prevention should cover dashboard users, public webhooks, and AI workflows.

Recommended controls:

- Rate-limit login, signup, organization creation, and invitation flows.
- Rate-limit webhook ingestion by source IP, app, phone number ID, and organization where possible.
- Validate payload sizes and reject unexpectedly large requests.
- Add allowlists or signature verification for provider webhooks.
- Detect duplicate webhook delivery and message IDs.
- Monitor unusual message volume, repeated failures, high AI cost, and repeated invalid signatures.
- Temporarily disable AI or ingestion for suspended organizations.

## Rate Limiting

Rate limits should be layered:

- Edge or reverse-proxy limits for public routes.
- Application-level limits by user ID, organization ID, route, and provider account ID.
- Provider-webhook limits that tolerate legitimate retries but block floods.
- AI-specific limits by organization subscription and current usage.

Rate-limit responses should avoid leaking whether a given organization or provider account exists.

## Audit Logging Strategy

Audit logging is deferred in schema, but the implementation should add it before sensitive service-role workflows expand.

Audit events should capture:

- `organization_id` when applicable.
- Actor type: user, system, webhook, worker, platform_admin.
- Actor ID or provider account ID.
- Action name.
- Affected table and record ID.
- Request ID, job ID, webhook delivery ID, or external event ID.
- Before/after metadata for sensitive changes where appropriate.
- Timestamp and outcome.

Actions that should be audited:

- Membership and role changes.
- Organization settings changes.
- WhatsApp connect/disconnect/reconnect.
- Provider token rotation.
- Customer identity merge/reassignment/deletion.
- Service-role privacy redaction or deletion.
- AI enable/disable and quota override changes.
- Human handoff assignment and resolution.

## Secrets Management

Secrets must not be committed to the repository or placed in frontend bundles.

Secrets include:

- Supabase service-role keys.
- Meta app secret, verify token, and access tokens.
- OpenAI API keys.
- Webhook signing secrets.
- Database URLs with credentials.
- Encryption keys.

Requirements:

- Use server-side environment secrets or managed secret storage.
- Keep `.env` files local and untracked.
- Keep `.env.example` free of real secrets.
- Rotate secrets after suspected exposure.
- Limit production secret access by role.
- Do not log secrets, authorization headers, signed payloads, or full tokens.

## Data Retention And Deletion Policy

Retention rules should balance merchant utility, legal requirements, customer privacy, and debugging needs.

Recommended defaults:

- Keep message history while an organization is active unless the merchant requests deletion or a retention limit is configured.
- Retain provider delivery IDs and idempotency keys long enough to safely handle retries and audits.
- Retain AI interaction usage records for billing and cost analysis.
- Redact or delete customer personal data on approved deletion requests.
- Prefer tombstones for immutable message timelines when deletion would break auditability.
- Delete or anonymize raw provider payloads after their debugging value expires.
- Support organization-level export and deletion workflows before production launch.

Deletion workflows must be service-role controlled, audited, and organization-scoped.

## Human Handoff Rules

Human handoff is a safety boundary as well as an operations feature.

AI should stop or avoid replying when:

- A customer asks for a human.
- The conversation is assigned to a human and handoff status is active.
- The customer raises payment, refund, legal, safety, abuse, or account-identity issues.
- The model is uncertain about product availability, price, delivery promise, or policy-sensitive claims.
- The organization has exceeded AI quota or disabled AI automation.
- The incoming content appears malicious, attempts prompt injection, or requests internal data.

During handoff:

- Messages continue to be persisted.
- AI analysis may run only if allowed by policy and quota.
- No outbound AI message should be sent until handoff is resolved.
- Assignment and handoff status changes should be audited.

## Open Security Questions

- Which exact audit table name and schema should be used: `audit_events`, `admin_audit_log`, or separate security and operational logs?
- Should WhatsApp account mappings live in `whatsapp_accounts` or a generic `organization_integrations` table?
- Which gateway or middleware will enforce rate limiting in production?
- What is the exact retention period for raw provider payloads?
- What roles can enable AI auto-replies once Phase 5B begins?
- What customer deletion workflow is required for Indian sellers and future international markets?


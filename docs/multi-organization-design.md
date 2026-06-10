# Multi-Organization Design

OmniBot V3 is designed as a shared application where each Instagram fashion seller operates as an isolated organization. Organization isolation is a product, security, billing, and data modeling requirement.

Backend and database terminology must use organization language. The approved database boundary is `organization_id`. Do not use `tenant_id` in backend, database, repository, service, route, or schema contracts.

UI and customer-facing copy may use "brand" where that language is clearer for Instagram fashion sellers. Backend and database contracts must use "organization".

## Organization Model

An organization represents one seller account. All business-owned resources belong to an organization, including integration accounts, customers, conversations, messages, knowledge base content, analytics, and subscriptions.

Dashboard users can belong to one or more organizations through memberships. A user should never receive access to organization data only because they are authenticated; access must depend on an active membership and role.

## Isolation Strategy

The primary isolation model is shared infrastructure with organization-scoped rows:

- A shared Supabase project hosts all organizations.
- Organization-owned tables include `organization_id`.
- Row Level Security policies restrict organization data access.
- Application APIs must resolve the active organization before executing business logic.
- Background jobs and webhooks must explicitly scope every operation to an organization.

This model supports efficient onboarding and operations while keeping organization data boundaries clear.

## Organization Resolution

Organization resolution depends on the entry point.

For dashboard requests:

- The authenticated user selects or operates within an active organization.
- The API verifies the user's membership and role for that organization.
- Queries are scoped to the active `organization_id`.

For WhatsApp webhooks:

- The webhook identifies the organization using WhatsApp identifiers such as `phone_number_id` or `whatsapp_business_account_id`.
- The resolved organization is attached to the message processing context.
- All customer, conversation, message, AI, and analytics records are written with that `organization_id`.

For billing webhooks:

- The billing provider customer or subscription ID maps back to one organization.
- Subscription status and entitlements are updated only for that organization.

## Access Control

Organization roles should define what dashboard users can view or change.

Suggested roles:

- `owner`: Full organization control, billing access, member management.
- `admin`: Operational control without ownership transfer.
- `agent`: Customer and conversation management.
- `viewer`: Read-only access to dashboards and reports.

Sensitive actions should require elevated roles, including billing changes, WhatsApp reconnection, member invitations, and knowledge base deletion.

## Data Boundaries

Organization-scoped data:

- Integration metadata.
- Customer profiles.
- Conversations and messages.
- Knowledge sources, chunks, and embeddings.
- AI run logs.
- Analytics events.
- Usage records and subscription state.

Platform-level data:

- Global plan definitions.
- System configuration.
- Provider webhook logs that are not organization-specific until resolved.
- Operational audit metadata used by platform administrators.

## RAG Isolation

RAG retrieval must always include `organization_id` as a hard filter before ranking or returning knowledge chunks. An organization's AI agent must never search across global embeddings unless that content is explicitly designed as shared platform knowledge.

Knowledge ingestion should preserve organization ownership across every derived artifact:

- Source file or URL.
- Parsed document text.
- Chunk records.
- Embedding records.
- Retrieval logs.

## Billing and Entitlements

Entitlements should be evaluated per organization. Before processing AI responses or high-volume messaging workflows, the platform should check:

- Subscription status.
- Plan limits.
- Usage for the current billing period.
- Feature availability.
- Trial or grace-period rules.

Usage records should be organization-scoped so invoices, analytics, and enforcement decisions are traceable.

## Security Requirements

- Enable Row Level Security on organization-owned tables.
- Store provider tokens through encrypted storage or a managed secret reference.
- Validate WhatsApp webhook signatures.
- Validate billing webhook signatures.
- Keep service-role database access out of browser clients.
- Log security-sensitive admin actions.
- Avoid exposing raw provider credentials in dashboard responses.

## Operational Requirements

- Webhook handlers should be idempotent.
- Message processing should tolerate retries and out-of-order delivery.
- Organization onboarding should track integration status clearly.
- Failed AI, WhatsApp, billing, and ingestion operations should be visible to operators.
- Analytics should distinguish organization usage from platform-level operations.

## Deferred Schema

- WhatsApp integration mapping schema is deferred because WhatsApp onboarding is not part of the repository-layer objective. It will be added when WhatsApp webhook ingestion and account connection are implemented. The integration module will own it.
- `audit_events` or `admin_audit_log` is deferred because service-role write workflows and sensitive admin operations are not implemented yet. It will be added before those mutations are enabled. The security/compliance module will own it.
- `knowledge_sources`, `knowledge_chunks`, and embeddings are deferred because RAG ingestion and retrieval are not part of the repository-layer objective. They will be added when the knowledge base module is implemented. The knowledge/RAG module will own them.
- Billing provider mappings are deferred because provider selection and webhook handling are not implemented yet. They will be added when Stripe, Razorpay, or another provider is selected. The billing module will own them.

## Open Decisions

- Final application framework and deployment target.
- Billing provider.
- Exact Supabase Auth membership flow.
- Vector storage implementation details.
- Queue or background job provider.
- Admin support model for platform operators.

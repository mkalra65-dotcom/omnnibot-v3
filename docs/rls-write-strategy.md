# RLS Write Strategy

This document defines the intended Row Level Security strategy for OmniBot V3. It is documentation only; broad write policies should not be enabled until application authorization, role semantics, and audit requirements are finalized.

## Security Model

OmniBot V3 uses shared infrastructure with strict organization-scoped rows. Business-owned tables include `organization_id`. Authenticated dashboard users gain access through active rows in `memberships`. Backend workers and webhooks use service-role credentials, but must still enforce organization resolution and role checks in application code.

Core principles:

- Browser clients should not use service-role keys.
- SELECT policies can expose organization data to active members.
- INSERT, UPDATE, and DELETE policies should be role-specific and narrow.
- Service-role writes must be audited for sensitive mutations.
- Every write path must resolve exactly one organization before mutation.

## Table-by-Table RLS Strategy

| Table | SELECT | INSERT | UPDATE | DELETE |
| --- | --- | --- | --- | --- |
| `organizations` | Active members can read their organization. | Service role only during onboarding; future owner-created org policy can be added. | Owner/admin via service role or narrow policy. | Soft-delete/archive only; hard delete service role only. |
| `memberships` | Active members can read memberships in their organization. | Owner/admin invitation path via service role. | Owner/admin can update roles/status through service role. | Prefer disable status; hard delete service role only. |
| `customers` | Active members can read organization customers. | Agent/admin/owner through service role after membership check. | Agent/admin/owner through service role; restrict lead score and LTV updates to trusted backend jobs. | Prefer archive; hard delete service role only. |
| `customer_identities` | Active members can read organization identities. | Trusted backend/channel resolver only; avoid direct client insert. | Trusted backend only to merge or correct identities. | Trusted backend only; normally retain for audit. |
| `conversations` | Active members can read organization conversations. | Trusted backend or authenticated agent action through service role. | Agent/admin/owner can update status, assignment, and state through service role. | Prefer archive; hard delete service role only. |
| `messages` | Active members can read organization message history. | Trusted backend only for webhook/outbound/human-message recording. | Trusted backend only for delivery status and metadata updates. | No normal deletes; redact or tombstone through service role. |
| `products` | Active members can read organization catalog. | Admin/manager/owner through service role. | Admin/manager/owner through service role. | Prefer archive; hard delete service role only. |
| `faq_entries` | Active members can read organization FAQs. | Admin/manager/owner through service role. | Admin/manager/owner through service role. | Prefer archive; hard delete service role only. |
| `lead_events` | Active members can read organization lead history. | Trusted backend only; event-sourced records should be append-only. | No normal updates except metadata correction by service role. | No normal deletes; retention policy only. |
| `ai_interactions` | Active members can read organization AI cost/debug records. | Trusted backend only. | Trusted backend only for late status/error updates. | Retention/archive only. |
| `merchant_feedback` | Active members can read organization feedback. | Authenticated members through service role after membership check. | Normally immutable; service role only for redaction. | Service role only for privacy/redaction workflows. |

## Additional Tables

| Table | SELECT | INSERT | UPDATE | DELETE |
| --- | --- | --- | --- | --- |
| `message_ai_analysis` | Active members can read organization analysis. | Trusted backend only. | Trusted backend only when re-analysis replaces current analysis. | Retention/archive only. |
| `ai_feedback` | Active members can read organization feedback. | Authenticated members through service role. | Normally immutable; service role only. | Service role only. |
| `conversion_events` | Active members can read organization conversion history. | Trusted backend only; append-only. | No normal updates except correction metadata. | Retention/archive only. |
| `organization_usage_daily` | Active members can read organization usage. | Trusted backend rollup job only. | Trusted backend rollup job only. | Service role only. |
| `automation_events` | Active members can read organization automation events. | Trusted backend scheduler only. | Trusted backend scheduler only. | Retention/archive only. |
| `subscription_plans` | Authenticated users can read active plans. | Platform admin/service role only. | Platform admin/service role only. | Archive only. |
| `organization_subscriptions` | Active members can read their organization's subscription. | Service role only. | Service role only. | Service role only. |

## Service Role Requirements

Service-role operations are required for:

- Webhook ingestion.
- Message delivery status updates.
- AI interaction and analysis writes.
- Usage rollups.
- Subscription state changes.
- Identity merge/correction.
- Automation scheduling and execution.
- Privacy redaction and retention workflows.

Every service-role mutation should log:

- `organization_id`
- actor or system component
- mutation type
- affected table and record ID
- request or job ID
- timestamp

## Recommended Future Write Policies

When direct client writes are eventually needed, add helper functions such as:

- `is_org_owner(organization_id)`
- `has_org_role(organization_id, roles membership_role[])`
- `can_manage_catalog(organization_id)`
- `can_manage_conversations(organization_id)`

Then add narrow policies by command. Avoid one broad `FOR ALL` policy on organization-owned tables.

## Repository Implementation Rules

- All organization-scoped repositories must require `organization_id` or a `TenantContext` carrying `organization_id`.
- No repository method may return organization-scoped data without organization scoping.
- Service-role writes must be called only behind service-layer authorization.
- `X-Organization-ID` is untrusted until membership is verified.
- Repositories must not contain business logic, AI logic, or external API calls.
- Repositories must not infer authorization from authentication alone.
- Repository reads by child IDs must also scope by `organization_id`.

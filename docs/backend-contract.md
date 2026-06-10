# Backend Contract

This document records the approved backend and repository-layer contract for OmniBot V3 after CTO Review Revision 1. It defines structure, schema ownership, repository implementation rules, and API surface only. Business logic, AI logic, WhatsApp integration, Instagram integration, payments, and followups are intentionally not implemented here.

Backend and database terminology must use organization language. The approved organization boundary is `organization_id`. Do not use `tenant_id` in backend, database, repository, service, route, or schema contracts.

UI and customer-facing copy may use "brand" where that language is clearer for Instagram fashion sellers. Backend and database contracts must use "organization".

## Current Phase

Current phase: Repository layer.

Approved inputs:

- Schema approved.
- Migrations approved.
- Active migration sequence:
  - `supabase/migrations/202606040001_sprint_1_foundation.sql`
  - `supabase/migrations/202606040002_cto_revision_1.sql`

Next objective: implement repositories that match the approved Revision 1 schema without adding application routes, service workflows, AI logic, external API calls, or new migrations.

## Folder Structure Target

```text
backend/
  app/
    api/
      dependencies.py
      v1/
        router.py
        routes/
          auth.py
          conversations.py
          customers.py
          faq_entries.py
          health.py
          memberships.py
          messages.py
          organizations.py
          products.py
    core/
      config.py
      supabase.py
    repositories/
      base.py
      ai_feedback.py
      ai_interactions.py
      automation_events.py
      conversations.py
      conversion_events.py
      customer_identities.py
      customers.py
      faq_entries.py
      lead_events.py
      memberships.py
      merchant_feedback.py
      message_ai_analysis.py
      messages.py
      organization_subscriptions.py
      organization_usage_daily.py
      organizations.py
      products.py
      subscription_plans.py
      users.py
    schemas/
      auth.py
      base.py
      conversations.py
      customer_identities.py
      customers.py
      faq_entries.py
      lead_events.py
      memberships.py
      merchant_feedback.py
      messages.py
      organizations.py
      products.py
      subscriptions.py
      users.py
    services/
      auth.py
      base.py
      conversations.py
      customers.py
      faq_entries.py
      memberships.py
      messages.py
      organizations.py
      products.py
    main.py
  .env.example
  README.md
  requirements.txt
supabase/
  migrations/
    202606040001_sprint_1_foundation.sql
    202606040002_cto_revision_1.sql
```

The repository list above is ownership guidance for implementation. It does not require creating all files before they are needed, but any implemented repository must follow the rules in this document.

## Approved Schema

### Foundation Migration

`supabase/migrations/202606040001_sprint_1_foundation.sql` defines:

- PostgreSQL extensions and enums.
- `organizations`
- `users`
- `memberships`
- `customers`
- `conversations`
- `messages`
- `products`
- `faq_entries`
- `message_ai_analysis`
- `ai_interactions`
- `ai_feedback`
- `conversion_events`
- `organization_usage_daily`
- `automation_events`
- Organization membership helper function for RLS.
- Updated-at triggers.
- Organization-scoped indexes.
- Row Level Security enablement and read policies.

### CTO Review Revision 1 Migration

`supabase/migrations/202606040002_cto_revision_1.sql` adds:

- `customer_identities`
- `lead_stage` enum and `customers.lead_stage`
- `lead_events`
- `merchant_feedback`
- `subscription_plans`
- `organization_subscriptions`
- `conversations.last_ai_response_at`
- `conversations.last_customer_response_at`

Revision 1 removes the legacy identity columns from `customers`:

- `customers.whatsapp_user_id`
- `customers.whatsapp_phone_number`
- `customers.instagram_user_id`
- `customers.instagram_username`

Provider identities now belong in `customer_identities`.

## Repository Ownership

| Repository | Owns |
| --- | --- |
| `organizations.py` | `organizations` |
| `users.py` | `users` |
| `memberships.py` | `memberships` |
| `customers.py` | `customers` |
| `customer_identities.py` | `customer_identities` |
| `conversations.py` | `conversations` |
| `messages.py` | `messages` |
| `products.py` | `products` |
| `faq_entries.py` | `faq_entries` |
| `message_ai_analysis.py` | `message_ai_analysis` |
| `ai_interactions.py` | `ai_interactions` |
| `ai_feedback.py` | `ai_feedback` |
| `merchant_feedback.py` | `merchant_feedback` |
| `conversion_events.py` | `conversion_events` |
| `lead_events.py` | `lead_events` |
| `organization_usage_daily.py` | `organization_usage_daily` |
| `automation_events.py` | `automation_events` |
| `subscription_plans.py` | `subscription_plans` |
| `organization_subscriptions.py` | `organization_subscriptions` |

Repositories should own persistence operations only. Cross-table workflows belong in services or database RPCs when implementation reaches that phase.

## Repository Implementation Rules

- All organization-scoped repositories must require `organization_id` or a `TenantContext` carrying `organization_id`.
- No repository method may return organization-scoped data without organization scoping.
- Service-role writes must be called only behind service-layer authorization.
- `X-Organization-ID` is untrusted until membership is verified.
- Repositories must not contain business logic, AI logic, or external API calls.
- Repositories must not infer authorization from authentication alone.
- Repository methods that write organization-scoped rows must write exactly one `organization_id`.
- Repository methods that read by child IDs, such as `customer_id`, `conversation_id`, or `message_id`, must also scope by `organization_id`.
- Idempotent provider/event writes must use the approved unique keys rather than ad hoc duplicate checks.

## Route Map

Base prefix: `/api/v1`

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| GET | `/health` | Health check | Implemented |
| POST | `/auth/signup` | Signup skeleton | 501 |
| POST | `/auth/login` | Login skeleton | 501 |
| POST | `/organizations` | Create organization skeleton | 501 |
| GET | `/organizations` | List organizations skeleton | 501 |
| GET | `/organizations/{organization_id}` | Get organization skeleton | 501 |
| PATCH | `/organizations/{organization_id}` | Update organization skeleton | 501 |
| POST | `/memberships` | Create membership skeleton | 501 |
| GET | `/memberships` | List memberships skeleton | 501 |
| GET | `/memberships/{membership_id}` | Get membership skeleton | 501 |
| PATCH | `/memberships/{membership_id}` | Update membership skeleton | 501 |
| POST | `/customers` | Create customer skeleton | 501 |
| GET | `/customers` | List customers skeleton | 501 |
| GET | `/customers/{customer_id}` | Get customer skeleton | 501 |
| PATCH | `/customers/{customer_id}` | Update customer skeleton | 501 |
| POST | `/conversations` | Create conversation skeleton | 501 |
| GET | `/conversations` | List conversations skeleton | 501 |
| GET | `/conversations/{conversation_id}` | Get conversation skeleton | 501 |
| PATCH | `/conversations/{conversation_id}` | Update conversation skeleton | 501 |
| POST | `/messages` | Create message skeleton | 501 |
| GET | `/messages` | List messages skeleton | 501 |
| GET | `/messages/{message_id}` | Get message skeleton | 501 |
| PATCH | `/messages/{message_id}` | Update message skeleton | 501 |
| POST | `/products` | Create product skeleton | 501 |
| GET | `/products` | List products skeleton | 501 |
| GET | `/products/{product_id}` | Get product skeleton | 501 |
| PATCH | `/products/{product_id}` | Update product skeleton | 501 |
| POST | `/faq-entries` | Create FAQ entry skeleton | 501 |
| GET | `/faq-entries` | List FAQ entries skeleton | 501 |
| GET | `/faq-entries/{faq_entry_id}` | Get FAQ entry skeleton | 501 |
| PATCH | `/faq-entries/{faq_entry_id}` | Update FAQ entry skeleton | 501 |

Organization-scoped routes require:

```http
X-Organization-ID: <organization uuid>
```

The header identifies the requested organization context only. It is not trusted authorization. The API must verify the authenticated user's active membership before any repository call that reads or writes organization-scoped data.

## API Contract Examples

### Auth

`SignupRequest`

```json
{
  "email": "seller@example.com",
  "password": "string",
  "full_name": "Seller Name",
  "organization_name": "Fashion Store"
}
```

`LoginRequest`

```json
{
  "email": "seller@example.com",
  "password": "string"
}
```

### Organization

```json
{
  "name": "Fashion Store",
  "slug": "fashion-store",
  "status": "active",
  "metadata": {}
}
```

### Membership

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "user_id": "00000000-0000-0000-0000-000000000000",
  "role": "owner",
  "status": "active"
}
```

### Customer

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "display_name": "Customer Name",
  "email": null,
  "phone_number": "+919999999999",
  "status": "lead",
  "lead_stage": "NEW",
  "purchase_stage": "unknown",
  "tags": [],
  "profile": {},
  "metadata": {}
}
```

Legacy provider identity fields are removed from `customers`. Use `customer_identities` for WhatsApp, Instagram, Facebook, website, email, and future provider identifiers.

### Customer Identity

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "customer_id": "00000000-0000-0000-0000-000000000000",
  "provider": "instagram",
  "provider_user_id": "17841400000000000",
  "provider_username": "fashion_store_customer",
  "provider_phone": null,
  "metadata": {}
}
```

### Conversation

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "customer_id": "00000000-0000-0000-0000-000000000000",
  "channel": "instagram",
  "status": "open",
  "handoff_status": "ai",
  "priority": "normal",
  "assigned_membership_id": null,
  "state": {},
  "metadata": {}
}
```

### Message

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "conversation_id": "00000000-0000-0000-0000-000000000000",
  "customer_id": "00000000-0000-0000-0000-000000000000",
  "channel": "instagram",
  "direction": "inbound",
  "sender_type": "customer",
  "message_type": "text",
  "body": "Do you have this in medium?",
  "external_message_id": null,
  "status": "received",
  "provider_payload": {},
  "metadata": {}
}
```

### Product

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "name": "Cotton Kurti",
  "sku": "KURTI-001",
  "description": "Cotton kurti with printed pattern",
  "category": "Kurtis",
  "color": "Blue",
  "size": "M",
  "price": "1499.00",
  "currency": "INR",
  "inventory_quantity": 10,
  "image_url": null,
  "status": "active",
  "metadata": {}
}
```

### FAQ Entry

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "question": "Do you offer exchanges?",
  "answer": "Exchange policy details go here.",
  "category": "returns",
  "status": "active",
  "metadata": {}
}
```

### Lead Event

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "customer_id": "00000000-0000-0000-0000-000000000000",
  "conversation_id": "00000000-0000-0000-0000-000000000000",
  "lead_stage": "INTERESTED",
  "event_type": "PRODUCT_INTEREST",
  "metadata": {}
}
```

### Merchant Feedback

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "ai_interaction_id": "00000000-0000-0000-0000-000000000000",
  "original_response": "Original AI response.",
  "edited_response": "Merchant edited response.",
  "feedback_type": "edited_ai_response"
}
```

### Subscription Plan

```json
{
  "name": "Growth",
  "slug": "growth",
  "status": "active",
  "monthly_message_limit": 5000,
  "monthly_ai_request_limit": 2500,
  "monthly_token_limit": 2500000,
  "metadata": {}
}
```

### Organization Subscription

```json
{
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "subscription_plan_id": "00000000-0000-0000-0000-000000000000",
  "status": "trialing",
  "current_period_start": "2026-06-01",
  "current_period_end": "2026-06-30",
  "metadata": {}
}
```

## Deferred Schema

### WhatsApp Integration Mapping Schema

Deferred because the current target market is Instagram fashion sellers and the approved schema does not yet need provider credential or webhook routing tables. It will be added when WhatsApp onboarding and webhook ingestion are implemented. The integration module will own it.

Expected future ownership: integration repositories and services, likely including tables for organization provider accounts, WhatsApp phone number IDs, WABA IDs, connection status, and encrypted secret references.

### Audit Events / Admin Audit Log

Deferred because service-role write surfaces and admin workflows are not implemented yet. It will be added before sensitive admin mutations, billing changes, integration reconnects, role changes, or privacy workflows are enabled. The security/compliance module will own it.

Expected future ownership: audit repository and service, with records for `organization_id`, actor, action, target table, target ID, request or job ID, and timestamp.

### Knowledge Sources / Knowledge Chunks / Embeddings

Deferred because RAG ingestion and retrieval are not part of the repository-layer objective. It will be added when knowledge base ingestion, chunking, embedding generation, and retrieval are implemented. The knowledge/RAG module will own it.

Expected future ownership: knowledge repositories and services, with every source, chunk, embedding, and retrieval log scoped by `organization_id`.

### Billing Provider Mappings

Deferred because the current subscription schema intentionally models plans and organization subscription state without coupling to Stripe, Razorpay, or another payment provider. It will be added when a billing provider is selected and webhook handling is implemented. The billing module will own it.

Expected future ownership: billing repositories and services, likely including provider customer IDs, provider subscription IDs, invoice/payment references, webhook event IDs, and reconciliation metadata.

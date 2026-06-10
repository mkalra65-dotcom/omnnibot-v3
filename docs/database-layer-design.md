# OmniBot V3 Database Layer Design

This document defines the production database architecture for OmniBot V3. It covers schema design only and intentionally excludes application code, APIs, repositories, services, AI implementation, channel integrations, and frontend behavior.

## 1. Executive Summary

Revision 1 keeps the approved multi-organization foundation and makes it more scalable for a sales operating system:

- Customer channel identifiers move out of `customers` into `customer_identities`, so WhatsApp, Instagram, Facebook, website, email, and future channels can coexist without widening the customer table.
- `purchase_stage` remains the AI-inferred buyer psychology signal, while `lead_stage` becomes the merchant/CRM pipeline state.
- `lead_events` adds an event-sourced sales funnel timeline for analytics, attribution, finance scoring, and future lending signals.
- `merchant_feedback` captures edited AI responses as high-value supervised training data for prompt optimization and future fine-tuning.
- `subscription_plans` and `organization_subscriptions` provide a simple SaaS billing foundation without payment-provider coupling.
- `conversations.last_ai_response_at` and `conversations.last_customer_response_at` prepare the data model for follow-ups, lead aging, hot-lead detection, and abandoned-conversation analysis.
- RLS remains strict on SELECT and conservative on writes; backend service-role writes must enforce organization membership and role checks until final role semantics are implemented.

## 2. SQL Migration Changes Only

The active migration sequence is:

- `supabase/migrations/202606040001_sprint_1_foundation.sql`
- `supabase/migrations/202606040002_cto_revision_1.sql`

Revision 1 adds:

- `customer_identities`
- `lead_stage` enum and `customers.lead_stage`
- `lead_events`
- `merchant_feedback`
- `subscription_plans`
- `organization_subscriptions`
- `conversations.last_ai_response_at`
- `conversations.last_customer_response_at`

Revision 1 migrates legacy customer identity columns into `customer_identities`, then drops:

- `customers.whatsapp_user_id`
- `customers.whatsapp_phone_number`
- `customers.instagram_user_id`
- `customers.instagram_username`

## 3. Updated ERD

```text
auth.users
  1:1 users

organizations
  1:N memberships
  1:N customers
  1:N customer_identities
  1:N conversations
  1:N messages
  1:N products
  1:N faq_entries
  1:N ai_interactions
  1:N message_ai_analysis
  1:N ai_feedback
  1:N merchant_feedback
  1:N conversion_events
  1:N lead_events
  1:N organization_usage_daily
  1:N automation_events
  1:N organization_subscriptions

subscription_plans
  1:N organization_subscriptions

users
  1:N memberships
  1:N messages.sender_user_id
  1:N ai_feedback.submitted_by_user_id

memberships
  1:N conversations.assigned_membership_id

customers
  1:N customer_identities
  1:N conversations
  1:N messages
  1:N conversion_events
  1:N lead_events
  1:N automation_events

customer_identities
  N:1 customers

conversations
  1:N messages
  1:N ai_interactions
  1:N message_ai_analysis
  1:N ai_feedback
  1:N conversion_events
  1:N lead_events
  1:N automation_events

messages
  1:1 message_ai_analysis
  1:N ai_interactions
  1:N ai_feedback
  1:N conversion_events
  1:N automation_events

products
  1:N conversion_events

ai_interactions
  1:N ai_feedback
  1:N merchant_feedback
  1:N message_ai_analysis
```

## 4. Design Rationale for Every Revision 1 Change

### Customer Identities

Moving channel identifiers into `customer_identities` prevents schema churn as new channels arrive. A customer can have many identities across WhatsApp, Instagram, Facebook, email, website chat, and future surfaces. The table is organization-scoped and has composite organization-safe foreign keys, so an identity cannot point to a customer in another organization.

Migration path:

- Legacy WhatsApp user/phone fields are inserted as `provider = 'whatsapp'`.
- Legacy Instagram user/username fields are inserted as `provider = 'instagram'`.
- Legacy identity-specific customer columns and indexes are dropped after backfill.

### Lead Stage Pipeline

`purchase_stage` and `lead_stage` represent different concepts:

- `purchase_stage`: AI interpretation of buying psychology, such as awareness, interest, consideration, intent, purchased, or lost.
- `lead_stage`: CRM pipeline state owned by the business process, such as NEW, ENGAGED, INTERESTED, PAYMENT_SENT, WON, or LOST.

Both exist because AI understanding and sales workflow are related but not identical. A customer can sound high-intent while still being operationally NEW, or can be in PAYMENT_SENT while the latest message sentiment is hesitant.

### Lead Events

`lead_events` creates an event-sourced funnel timeline. It supports analytics, attribution, finance scoring, future lending, and auditability without overwriting historical state. `customers.lead_stage` is the current state; `lead_events` is the state-change and signal history.

### Merchant Feedback

`merchant_feedback` captures cases where a merchant edits, rejects, approves, or corrects an AI output. This is stronger than a simple thumbs-up/down table because it stores original and edited responses. Over time this becomes an AI moat: the platform accumulates merchant-specific and category-specific examples of what good selling responses look like, enabling prompt optimization, evaluation datasets, routing rules, and future fine-tuning.

### Subscription Foundation

`subscription_plans` and `organization_subscriptions` model billing entitlements without payment-provider integration. Starter, Growth, and Pro plans define monthly limits for messages, AI requests, and token usage. The model can later attach Stripe/Razorpay/customer IDs without changing usage-tracking fundamentals.

### Follow-Up Readiness

`conversations.last_ai_response_at` and `conversations.last_customer_response_at` support:

- Follow-ups: find conversations where AI replied but the customer has not responded.
- Lead aging: identify stale conversations by customer-response recency.
- Hot lead detection: combine recent customer response with high lead score and intent.
- Abandoned conversations: detect payment or product-interest states without customer response.

## 5. Updated Index Strategy

### New Revision 1 Indexes

- `idx_customers_org_lead_stage_updated`: powers CRM pipeline views by organization and lead stage.
- `idx_conversations_org_last_ai_response`: finds conversations awaiting customer response after AI reply.
- `idx_conversations_org_last_customer_response`: finds recently active or aging customer conversations.
- `idx_customer_identities_org_customer`: loads all identities for a customer.
- `uq_customer_identities_provider_user`: unique lookup by organization, provider, and provider user ID.
- `uq_customer_identities_provider_username`: unique lookup by organization, provider, and provider username.
- `uq_customer_identities_provider_phone`: unique lookup by organization, provider, and provider phone.
- `idx_lead_events_org_stage_created`: supports stage analytics and pipeline history.
- `idx_lead_events_org_type_created`: supports funnel event reporting.
- `idx_lead_events_customer_created`: supports customer timeline views.
- `idx_lead_events_conversation_created`: supports conversation-level funnel history.
- `idx_merchant_feedback_org_created`: supports feedback review and training data export.
- `idx_merchant_feedback_ai_interaction`: links feedback to model calls.
- `idx_subscription_plans_status`: lists active plans.
- `idx_organization_subscriptions_org_status`: resolves current subscription state for an organization.
- `idx_organization_subscriptions_plan_status`: supports plan-level reporting.
- `uq_organization_subscriptions_active_org`: enforces one active/trialing/past-due subscription per organization.

### Existing High-Value Indexes

- Message indexes remain centered on `(organization_id, created_at)`, `(conversation_id, created_at)`, and provider retry IDs.
- Product indexes enforce catalog lookup by organization, SKU, status, category, and inventory.
- FAQ indexes enforce normalized question uniqueness and category browsing.
- AI indexes support cost tracking by organization, model, conversation, and message.
- Conversion event indexes support organization-level funnels, customer timelines, conversation timelines, and product analytics.
- Automation indexes support future scheduled job polling.

## 6. Updated Uniqueness Strategy

- `customer_identities(organization_id, provider, provider_user_id) where provider_user_id is not null`: prevents one provider user from mapping to multiple customers in the same organization.
- `customer_identities(organization_id, provider, provider_username) where provider_username is not null`: prevents duplicate social handles per organization/provider.
- `customer_identities(organization_id, provider, provider_phone) where provider_phone is not null`: prevents duplicate phone identities per organization/provider.
- `organization_subscriptions(organization_id) where status in ('trialing', 'active', 'past_due')`: only one current billable subscription state per organization.
- Existing product normalized-name, product SKU, FAQ normalized-question, message provider ID, conversion event key, automation idempotency key, and daily usage uniqueness remain valid.

Partial unique indexes are used wherever provider identifiers can be null. This prevents false conflicts while preserving idempotency and lookup integrity.

## 7. Updated RLS Strategy

RLS has two layers:

- Database organization isolation: rows are scoped by `organization_id`, and `is_org_member(organization_id)` controls authenticated member visibility.
- Backend service-role enforcement: service-role writes must validate organization membership, role, and intended mutation before writing.

Write policies are intentionally not broadly opened until final product authorization semantics are finalized. Direct client writes should be avoided for business-owned data.

See `docs/rls-write-strategy.md` for table-by-table SELECT, INSERT, UPDATE, and DELETE policy recommendations.

## 8. Future Scalability Review

### 10 Merchants

The schema will perform comfortably on a single Supabase Postgres instance. Main risks are product iteration speed and keeping RLS policies tested.

### 100 Merchants

Message and AI interaction volume becomes the first real growth area. Existing organization/time indexes are sufficient, but dashboards should query rollups where possible.

### 1,000 Merchants

Partition candidates become important:

- `messages`
- `ai_interactions`
- `lead_events`
- `conversion_events`
- `automation_events`

Analytics should move toward materialized views or rollup tables. Raw event queries should be avoided in dashboard hot paths.

### 10,000 Merchants

The main bottlenecks are write volume, index bloat, retention, and analytics fanout. At this stage:

- Partition high-volume tables by month or by hash/time hybrid.
- Archive old provider payloads and message metadata.
- Move heavy analytics into a warehouse or dedicated read model.
- Track AI cost at request level and reconcile against provider invoice exports.
- Consider separate operational and analytical databases.

## 9. Risks and Recommendations

- Risk: `customer_identities` can accumulate ambiguous identifiers if providers are not normalized. Recommendation: provider names must be lowercase and stable.
- Risk: enum-heavy design can slow taxonomy changes. Recommendation: keep enums only for stable operational states; move volatile categories into lookup tables later.
- Risk: merchant feedback can contain sensitive customer data. Recommendation: classify and redact before using it for training exports.
- Risk: daily usage rollups can drift from raw events. Recommendation: periodically reconcile `organization_usage_daily` with `messages` and `ai_interactions`.
- Risk: service-role writes can bypass RLS. Recommendation: centralize all service-role writes and log sensitive mutations.

## 10. Deferred Schema

- WhatsApp integration mapping schema is deferred because the repository-layer phase does not implement WhatsApp account connection or webhook routing. It will be added when the integration module implements WhatsApp onboarding and webhook ingestion.
- `audit_events` or `admin_audit_log` is deferred because sensitive admin mutations and service-role write workflows are not implemented yet. It will be added before those workflows are enabled and owned by the security/compliance module.
- `knowledge_sources`, `knowledge_chunks`, and embeddings are deferred because RAG ingestion and retrieval are outside the current repository-layer objective. They will be added when the knowledge/RAG module is implemented.
- Billing provider mappings are deferred because the schema intentionally models subscriptions without coupling to Stripe, Razorpay, or another provider. They will be added when the billing module selects and integrates a provider.

## 11. Final Schema Score

Score: 8.7 / 10

The schema is production-grade for an early SaaS platform and has clean expansion paths for commerce, follow-ups, analytics, subscriptions, and AI learning. The remaining work before a 9.5+ score is partition planning, final write RLS policies, explicit retention policies, and a future identity-normalization service once integrations are implemented.

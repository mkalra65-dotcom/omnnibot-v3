# Architecture

OmniBot V3 is a multi-organization AI commerce agent platform for Instagram fashion sellers that need automated customer conversations, onboarding, knowledge retrieval, analytics, and subscription billing.

## System Overview

The platform is organized around independent seller organizations. Each organization configures agent behavior, connects supported channels, uploads or manages knowledge content, and monitors customer conversations through an admin dashboard.

Core platform areas:

- Channel integration for inbound and outbound customer messaging.
- Organization onboarding for seller setup, channel connection, billing, and initial configuration.
- Admin dashboard for managing customers, conversations, knowledge, analytics, and account settings.
- AI agent runtime using OpenAI for conversation generation and RAG-backed answers.
- Supabase backend for authentication, relational data, storage, and operational APIs.
- Analytics pipeline for message volume, response quality, customer activity, and subscription usage.
- Billing layer for plans, subscriptions, limits, and entitlement enforcement.

## Logical Components

### Admin Dashboard

The admin dashboard is the primary interface for organization users. It should support organization setup, team access, channel connection status, customer records, conversations, knowledge base management, analytics, and subscription details.

### API Layer

The API layer coordinates dashboard requests, webhook processing, organization isolation checks, usage metering, billing state, and AI agent execution. All organization-scoped operations must resolve and enforce the active organization before reading or writing data.

### WhatsApp Cloud API Integration

The WhatsApp integration receives customer messages through webhooks, validates webhook authenticity, stores inbound messages, invokes the AI agent when automation is enabled, and sends replies through the WhatsApp Cloud API.

### AI Agent Runtime

The agent runtime builds conversation context from recent messages, organization configuration, customer profile data, and relevant knowledge base chunks. It calls OpenAI models to generate responses and records the model output, metadata, and usage.

### RAG Knowledge Base

The knowledge base stores organization-owned documents, normalized content, embeddings, and searchable chunks. Retrieval must be organization-scoped so one business can never retrieve another business's documents.

### Supabase Backend

Supabase provides the initial backend foundation:

- PostgreSQL for organization, customer, conversation, message, billing, and analytics data.
- Auth for dashboard users.
- Row Level Security for organization isolation.
- Storage for knowledge base source files.
- Edge functions or application APIs for webhook and background workflows.

### Billing and Entitlements

Billing tracks subscription plans, payment state, usage limits, and feature access. Runtime paths that create billable usage should check organization entitlements before performing expensive operations.

## Message Flow

1. A customer sends a message to an organization's connected channel.
2. WhatsApp Cloud API calls the platform webhook.
3. The webhook validates the request and resolves the organization from the provider account identifiers.
4. The platform stores the inbound message and updates or creates the customer record.
5. If automation is enabled and the organization has valid entitlements, the AI agent builds context.
6. The RAG layer retrieves organization-scoped knowledge chunks.
7. OpenAI generates the response.
8. The platform stores the assistant message and sends it through WhatsApp Cloud API.
9. Analytics and usage metrics are recorded.

## Operational Concerns

- Webhooks must be idempotent because WhatsApp may retry delivery.
- Organization isolation must be enforced in database policies and application logic.
- AI calls should be metered for billing, rate limits, and analytics.
- Knowledge ingestion should be asynchronous for larger files.
- Admin actions should be audited where they affect billing, integrations, or customer data.
- Sensitive tokens must be encrypted or stored in a managed secret store.

## Deferred Schema

- WhatsApp integration mapping schema is deferred until WhatsApp account connection and webhook ingestion are implemented. The integration module will own it.
- `audit_events` or `admin_audit_log` is deferred until sensitive admin mutations and service-role write workflows are implemented. The security/compliance module will own it.
- `knowledge_sources`, `knowledge_chunks`, and embeddings are deferred until RAG ingestion and retrieval are implemented. The knowledge/RAG module will own them.
- Billing provider mappings are deferred until a payment provider is selected and billing webhooks are implemented. The billing module will own them.

## Initial Non-Code Scope

This document describes the intended architecture only. Application code, framework selection, and implementation details should be added after the product and data model are finalized.

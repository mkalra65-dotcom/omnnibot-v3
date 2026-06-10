create type public.lead_stage as enum (
  'NEW',
  'ENGAGED',
  'INTERESTED',
  'PAYMENT_SENT',
  'WON',
  'LOST'
);

create type public.lead_event_type as enum (
  'LEAD_CREATED',
  'PRODUCT_INTEREST',
  'PRICE_DISCUSSION',
  'PAYMENT_REQUESTED',
  'PAYMENT_SENT',
  'PAYMENT_COMPLETED',
  'WON',
  'LOST'
);

create type public.merchant_feedback_type as enum (
  'edited_ai_response',
  'rejected_ai_response',
  'approved_ai_response',
  'prompt_gap',
  'product_gap',
  'policy_gap'
);

create type public.subscription_plan_status as enum ('active', 'archived');
create type public.organization_subscription_status as enum (
  'trialing',
  'active',
  'past_due',
  'cancelled',
  'expired'
);

alter table public.customers
add column lead_stage public.lead_stage not null default 'NEW';

alter table public.conversations
add column last_ai_response_at timestamptz,
add column last_customer_response_at timestamptz;

create table public.customer_identities (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  customer_id uuid not null references public.customers(id) on delete cascade,
  provider text not null,
  provider_user_id text,
  provider_username citext,
  provider_phone text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint customer_identities_provider_not_blank check (btrim(provider) <> ''),
  constraint customer_identities_provider_normalized check (provider = lower(provider)),
  constraint customer_identities_has_identifier check (
    provider_user_id is not null
    or provider_username is not null
    or provider_phone is not null
  )
);

alter table public.customer_identities
add constraint customer_identities_id_organization_id_unique unique (id, organization_id);

alter table public.customer_identities
add constraint customer_identities_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete cascade;

insert into public.customer_identities (
  organization_id,
  customer_id,
  provider,
  provider_user_id,
  provider_phone,
  metadata,
  created_at,
  updated_at
)
select
  organization_id,
  id,
  'whatsapp',
  whatsapp_user_id,
  whatsapp_phone_number,
  jsonb_build_object('source', 'customers_legacy_columns'),
  created_at,
  updated_at
from public.customers
where whatsapp_user_id is not null
   or whatsapp_phone_number is not null
on conflict do nothing;

insert into public.customer_identities (
  organization_id,
  customer_id,
  provider,
  provider_user_id,
  provider_username,
  metadata,
  created_at,
  updated_at
)
select
  organization_id,
  id,
  'instagram',
  instagram_user_id,
  instagram_username,
  jsonb_build_object('source', 'customers_legacy_columns'),
  created_at,
  updated_at
from public.customers
where instagram_user_id is not null
   or instagram_username is not null
on conflict do nothing;

create table public.lead_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  customer_id uuid not null references public.customers(id) on delete cascade,
  conversation_id uuid references public.conversations(id) on delete set null,
  lead_stage public.lead_stage not null,
  event_type public.lead_event_type not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.lead_events
add constraint lead_events_id_organization_id_unique unique (id, organization_id);

alter table public.lead_events
add constraint lead_events_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete cascade;

alter table public.lead_events
add constraint lead_events_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete set null (conversation_id);

create table public.merchant_feedback (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  ai_interaction_id uuid references public.ai_interactions(id) on delete set null,
  original_response text not null,
  edited_response text not null,
  feedback_type public.merchant_feedback_type not null default 'edited_ai_response',
  created_at timestamptz not null default now(),
  constraint merchant_feedback_original_not_blank check (btrim(original_response) <> ''),
  constraint merchant_feedback_edited_not_blank check (btrim(edited_response) <> '')
);

alter table public.merchant_feedback
add constraint merchant_feedback_id_organization_id_unique unique (id, organization_id);

alter table public.merchant_feedback
add constraint merchant_feedback_ai_interaction_tenant_fkey
foreign key (ai_interaction_id, organization_id)
references public.ai_interactions(id, organization_id) on delete set null (ai_interaction_id);

create table public.subscription_plans (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug citext not null unique,
  status public.subscription_plan_status not null default 'active',
  monthly_message_limit integer not null,
  monthly_ai_request_limit integer not null,
  monthly_token_limit integer not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint subscription_plans_name_not_blank check (btrim(name) <> ''),
  constraint subscription_plans_message_limit_positive check (monthly_message_limit > 0),
  constraint subscription_plans_ai_limit_positive check (monthly_ai_request_limit > 0),
  constraint subscription_plans_token_limit_positive check (monthly_token_limit > 0)
);

create table public.organization_subscriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  subscription_plan_id uuid not null references public.subscription_plans(id) on delete restrict,
  status public.organization_subscription_status not null default 'trialing',
  current_period_start date not null,
  current_period_end date not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_subscriptions_period_valid check (current_period_end >= current_period_start)
);

alter table public.organization_subscriptions
add constraint organization_subscriptions_id_organization_id_unique unique (id, organization_id);

insert into public.subscription_plans (
  name,
  slug,
  monthly_message_limit,
  monthly_ai_request_limit,
  monthly_token_limit
)
values
  ('Starter', 'starter', 1000, 500, 500000),
  ('Growth', 'growth', 5000, 2500, 2500000),
  ('Pro', 'pro', 20000, 10000, 10000000)
on conflict (slug) do nothing;

create trigger set_customer_identities_updated_at
before update on public.customer_identities
for each row execute function public.set_updated_at();

create trigger set_subscription_plans_updated_at
before update on public.subscription_plans
for each row execute function public.set_updated_at();

create trigger set_organization_subscriptions_updated_at
before update on public.organization_subscriptions
for each row execute function public.set_updated_at();

drop index if exists public.uq_customers_org_whatsapp_user_id;
drop index if exists public.uq_customers_org_whatsapp_phone_number;
drop index if exists public.uq_customers_org_instagram_user_id;
drop index if exists public.uq_customers_org_instagram_username;

alter table public.customers
drop column whatsapp_user_id,
drop column whatsapp_phone_number,
drop column instagram_user_id,
drop column instagram_username;

create index idx_customers_org_lead_stage_updated
on public.customers(organization_id, lead_stage, updated_at desc);

create index idx_conversations_org_last_ai_response
on public.conversations(organization_id, last_ai_response_at desc)
where last_ai_response_at is not null;

create index idx_conversations_org_last_customer_response
on public.conversations(organization_id, last_customer_response_at desc)
where last_customer_response_at is not null;

create index idx_customer_identities_org_customer
on public.customer_identities(organization_id, customer_id);

create unique index uq_customer_identities_provider_user
on public.customer_identities(organization_id, provider, provider_user_id)
where provider_user_id is not null;

create unique index uq_customer_identities_provider_username
on public.customer_identities(organization_id, provider, provider_username)
where provider_username is not null;

create unique index uq_customer_identities_provider_phone
on public.customer_identities(organization_id, provider, provider_phone)
where provider_phone is not null;

create index idx_lead_events_org_stage_created
on public.lead_events(organization_id, lead_stage, created_at desc);

create index idx_lead_events_org_type_created
on public.lead_events(organization_id, event_type, created_at desc);

create index idx_lead_events_customer_created
on public.lead_events(customer_id, created_at desc);

create index idx_lead_events_conversation_created
on public.lead_events(conversation_id, created_at desc)
where conversation_id is not null;

create index idx_merchant_feedback_org_created
on public.merchant_feedback(organization_id, created_at desc);

create index idx_merchant_feedback_ai_interaction
on public.merchant_feedback(ai_interaction_id)
where ai_interaction_id is not null;

create index idx_subscription_plans_status
on public.subscription_plans(status);

create index idx_organization_subscriptions_org_status
on public.organization_subscriptions(organization_id, status);

create index idx_organization_subscriptions_plan_status
on public.organization_subscriptions(subscription_plan_id, status);

create unique index uq_organization_subscriptions_active_org
on public.organization_subscriptions(organization_id)
where status in ('trialing', 'active', 'past_due');

alter table public.customer_identities enable row level security;
alter table public.lead_events enable row level security;
alter table public.merchant_feedback enable row level security;
alter table public.subscription_plans enable row level security;
alter table public.organization_subscriptions enable row level security;

create policy "members can read customer identities"
on public.customer_identities for select
using (public.is_org_member(organization_id));

create policy "members can read lead events"
on public.lead_events for select
using (public.is_org_member(organization_id));

create policy "members can read merchant feedback"
on public.merchant_feedback for select
using (public.is_org_member(organization_id));

create policy "authenticated users can read active subscription plans"
on public.subscription_plans for select
to authenticated
using (status = 'active');

create policy "members can read organization subscriptions"
on public.organization_subscriptions for select
using (public.is_org_member(organization_id));

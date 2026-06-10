create extension if not exists pgcrypto;
create extension if not exists citext;

create type public.organization_status as enum ('active', 'disabled', 'archived');
create type public.membership_role as enum ('owner', 'admin', 'manager', 'agent', 'viewer');
create type public.membership_status as enum ('active', 'invited', 'disabled');
create type public.customer_status as enum ('lead', 'customer', 'blocked', 'archived');
create type public.purchase_stage as enum ('unknown', 'awareness', 'interest', 'consideration', 'intent', 'purchased', 'lost');
create type public.channel_type as enum ('whatsapp', 'instagram', 'manual', 'web');
create type public.conversation_status as enum ('open', 'pending', 'closed', 'archived');
create type public.handoff_status as enum ('ai', 'human_requested', 'human_active', 'resolved');
create type public.conversation_priority as enum ('low', 'normal', 'high', 'urgent');
create type public.message_direction as enum ('inbound', 'outbound');
create type public.message_sender_type as enum ('customer', 'ai', 'human', 'system');
create type public.message_type as enum ('text', 'image', 'video', 'audio', 'document', 'interactive', 'template', 'system');
create type public.message_status as enum ('received', 'queued', 'sent', 'delivered', 'read', 'failed', 'deleted');
create type public.product_status as enum ('active', 'draft', 'out_of_stock', 'archived');
create type public.faq_status as enum ('active', 'draft', 'archived');
create type public.sentiment_label as enum ('positive', 'neutral', 'negative', 'mixed', 'unknown');
create type public.ai_interaction_type as enum ('message_analysis', 'reply_generation', 'classification', 'summarization', 'retrieval', 'other');
create type public.ai_interaction_status as enum ('success', 'failed', 'skipped');
create type public.ai_feedback_rating as enum ('positive', 'negative', 'neutral');
create type public.conversion_event_type as enum (
  'LEAD_CREATED',
  'PRODUCT_INTEREST',
  'PAYMENT_LINK_SENT',
  'PAYMENT_COMPLETED',
  'WON',
  'LOST'
);
create type public.automation_event_type as enum (
  'scheduled',
  'triggered',
  'skipped',
  'completed',
  'failed',
  'cancelled'
);
create type public.automation_event_status as enum ('pending', 'processing', 'completed', 'failed', 'cancelled');

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.normalize_text(value text)
returns text
language sql
immutable
as $$
  select nullif(regexp_replace(lower(btrim(coalesce(value, ''))), '\s+', ' ', 'g'), '');
$$;

create or replace function public.set_faq_normalized_question()
returns trigger
language plpgsql
as $$
begin
  new.normalized_question = public.normalize_text(new.question);
  return new;
end;
$$;

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug citext unique,
  status public.organization_status not null default 'active',
  default_currency char(3) not null default 'INR',
  timezone text not null default 'Asia/Kolkata',
  settings jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organizations_name_not_blank check (btrim(name) <> ''),
  constraint organizations_default_currency_uppercase check (default_currency = upper(default_currency))
);

create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email citext not null unique,
  full_name text,
  avatar_url text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  role public.membership_role not null default 'agent',
  status public.membership_status not null default 'active',
  invited_by_user_id uuid references public.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, user_id)
);

create table public.customers (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  display_name text,
  email citext,
  phone_number text,
  whatsapp_user_id text,
  whatsapp_phone_number text,
  instagram_user_id text,
  instagram_username citext,
  status public.customer_status not null default 'lead',
  lead_score numeric(5, 2) not null default 0,
  purchase_stage public.purchase_stage not null default 'unknown',
  lifetime_value_amount numeric(14, 2) not null default 0,
  lifetime_value_currency char(3) not null default 'INR',
  order_count integer not null default 0,
  first_purchase_at timestamptz,
  last_purchase_at timestamptz,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz,
  last_engaged_at timestamptz,
  tags text[] not null default '{}'::text[],
  profile jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint customers_lead_score_range check (lead_score >= 0 and lead_score <= 100),
  constraint customers_ltv_non_negative check (lifetime_value_amount >= 0),
  constraint customers_order_count_non_negative check (order_count >= 0),
  constraint customers_ltv_currency_uppercase check (lifetime_value_currency = upper(lifetime_value_currency))
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  customer_id uuid not null references public.customers(id) on delete cascade,
  channel public.channel_type not null,
  external_conversation_id text,
  status public.conversation_status not null default 'open',
  handoff_status public.handoff_status not null default 'ai',
  priority public.conversation_priority not null default 'normal',
  assigned_membership_id uuid references public.memberships(id) on delete set null,
  state jsonb not null default '{}'::jsonb,
  summary text,
  last_message_id uuid,
  last_message_at timestamptz,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  customer_id uuid references public.customers(id) on delete set null,
  channel public.channel_type not null,
  direction public.message_direction not null,
  sender_type public.message_sender_type not null,
  sender_user_id uuid references public.users(id) on delete set null,
  external_message_id text,
  external_event_id text,
  webhook_delivery_id text,
  message_type public.message_type not null default 'text',
  body text,
  media_url text,
  status public.message_status not null default 'received',
  generated_by_ai boolean not null default false,
  sent_by_human boolean not null default false,
  provider_payload jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  external_created_at timestamptz,
  sent_at timestamptz,
  delivered_at timestamptz,
  read_at timestamptz,
  failed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint messages_generation_source_consistent check (
    (sender_type = 'ai' and generated_by_ai = true and sent_by_human = false)
    or (sender_type = 'human' and sent_by_human = true and generated_by_ai = false)
    or (sender_type in ('customer', 'system'))
  )
);

alter table public.conversations
add constraint conversations_last_message_id_fkey
foreign key (last_message_id) references public.messages(id) on delete set null;

create table public.products (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  normalized_name text generated always as (public.normalize_text(name)) stored,
  sku text,
  description text,
  category text,
  brand text,
  color text,
  size text,
  material text,
  price numeric(14, 2),
  compare_at_price numeric(14, 2),
  currency char(3) not null default 'INR',
  inventory_quantity integer not null default 0,
  inventory_reserved integer not null default 0,
  inventory_low_stock_threshold integer,
  track_inventory boolean not null default true,
  image_url text,
  product_url text,
  status public.product_status not null default 'active',
  attributes jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint products_name_not_blank check (btrim(name) <> ''),
  constraint products_normalized_name_present check (normalized_name is not null),
  constraint products_price_non_negative check (price is null or price >= 0),
  constraint products_compare_price_non_negative check (compare_at_price is null or compare_at_price >= 0),
  constraint products_inventory_quantity_non_negative check (inventory_quantity >= 0),
  constraint products_inventory_reserved_non_negative check (inventory_reserved >= 0),
  constraint products_inventory_reserved_lte_quantity check (inventory_reserved <= inventory_quantity),
  constraint products_low_stock_non_negative check (inventory_low_stock_threshold is null or inventory_low_stock_threshold >= 0),
  constraint products_currency_uppercase check (currency = upper(currency))
);

create table public.faq_entries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  question text not null,
  normalized_question text not null,
  answer text not null,
  category text,
  status public.faq_status not null default 'active',
  usage_count integer not null default 0,
  last_used_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint faq_entries_question_not_blank check (btrim(question) <> ''),
  constraint faq_entries_normalized_question_not_blank check (btrim(normalized_question) <> ''),
  constraint faq_entries_answer_not_blank check (btrim(answer) <> ''),
  constraint faq_entries_usage_count_non_negative check (usage_count >= 0)
);

create table public.ai_interactions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid references public.conversations(id) on delete set null,
  message_id uuid references public.messages(id) on delete set null,
  interaction_type public.ai_interaction_type not null,
  status public.ai_interaction_status not null default 'success',
  provider text not null default 'openai',
  model text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  latency_ms integer,
  cost_estimate numeric(14, 6) not null default 0,
  request_id text,
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint ai_interactions_input_tokens_non_negative check (input_tokens >= 0),
  constraint ai_interactions_output_tokens_non_negative check (output_tokens >= 0),
  constraint ai_interactions_latency_non_negative check (latency_ms is null or latency_ms >= 0),
  constraint ai_interactions_cost_non_negative check (cost_estimate >= 0)
);

create table public.message_ai_analysis (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  message_id uuid not null references public.messages(id) on delete cascade,
  ai_interaction_id uuid references public.ai_interactions(id) on delete set null,
  intent text,
  intent_confidence numeric(5, 4),
  sentiment public.sentiment_label not null default 'unknown',
  sentiment_score numeric(5, 4),
  product_interest jsonb not null default '[]'::jsonb,
  budget_signals jsonb not null default '{}'::jsonb,
  purchase_stage public.purchase_stage not null default 'unknown',
  lead_score_delta numeric(6, 2) not null default 0,
  entities jsonb not null default '{}'::jsonb,
  analysis_version text,
  analyzed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint message_ai_analysis_intent_confidence_range check (intent_confidence is null or (intent_confidence >= 0 and intent_confidence <= 1)),
  constraint message_ai_analysis_sentiment_score_range check (sentiment_score is null or (sentiment_score >= -1 and sentiment_score <= 1)),
  unique (message_id)
);

create table public.ai_feedback (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  ai_interaction_id uuid references public.ai_interactions(id) on delete cascade,
  message_id uuid references public.messages(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  submitted_by_user_id uuid references public.users(id) on delete set null,
  rating public.ai_feedback_rating not null,
  reason text,
  corrected_response text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.conversion_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  customer_id uuid references public.customers(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  message_id uuid references public.messages(id) on delete set null,
  product_id uuid references public.products(id) on delete set null,
  event_type public.conversion_event_type not null,
  event_key text,
  value_amount numeric(14, 2),
  value_currency char(3),
  source_channel public.channel_type,
  actor_type text not null default 'system',
  actor_id uuid,
  properties jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint conversion_events_value_non_negative check (value_amount is null or value_amount >= 0),
  constraint conversion_events_currency_uppercase check (value_currency is null or value_currency = upper(value_currency))
);

create table public.organization_usage_daily (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  usage_date date not null,
  inbound_messages integer not null default 0,
  outbound_messages integer not null default 0,
  ai_requests integer not null default 0,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  total_tokens integer generated always as (input_tokens + output_tokens) stored,
  ai_cost_estimate numeric(14, 6) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, usage_date),
  constraint organization_usage_daily_inbound_non_negative check (inbound_messages >= 0),
  constraint organization_usage_daily_outbound_non_negative check (outbound_messages >= 0),
  constraint organization_usage_daily_ai_requests_non_negative check (ai_requests >= 0),
  constraint organization_usage_daily_input_tokens_non_negative check (input_tokens >= 0),
  constraint organization_usage_daily_output_tokens_non_negative check (output_tokens >= 0),
  constraint organization_usage_daily_cost_non_negative check (ai_cost_estimate >= 0)
);

create table public.automation_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  customer_id uuid references public.customers(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  message_id uuid references public.messages(id) on delete set null,
  automation_key text not null,
  event_type public.automation_event_type not null,
  status public.automation_event_status not null default 'pending',
  scheduled_for timestamptz,
  executed_at timestamptz,
  cancelled_at timestamptz,
  error_code text,
  error_message text,
  idempotency_key text,
  payload jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.memberships
add constraint memberships_id_organization_id_unique unique (id, organization_id);

alter table public.customers
add constraint customers_id_organization_id_unique unique (id, organization_id);

alter table public.conversations
add constraint conversations_id_organization_id_unique unique (id, organization_id);

alter table public.messages
add constraint messages_id_organization_id_unique unique (id, organization_id);

alter table public.products
add constraint products_id_organization_id_unique unique (id, organization_id);

alter table public.ai_interactions
add constraint ai_interactions_id_organization_id_unique unique (id, organization_id);

alter table public.conversations
add constraint conversations_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete cascade;

alter table public.conversations
add constraint conversations_assigned_membership_tenant_fkey
foreign key (assigned_membership_id, organization_id)
references public.memberships(id, organization_id) on delete set null (assigned_membership_id);

alter table public.conversations
add constraint conversations_last_message_tenant_fkey
foreign key (last_message_id, organization_id)
references public.messages(id, organization_id) on delete set null (last_message_id);

alter table public.messages
add constraint messages_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete cascade;

alter table public.messages
add constraint messages_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete set null (customer_id);

alter table public.message_ai_analysis
add constraint message_ai_analysis_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete cascade;

alter table public.message_ai_analysis
add constraint message_ai_analysis_message_tenant_fkey
foreign key (message_id, organization_id)
references public.messages(id, organization_id) on delete cascade;

alter table public.message_ai_analysis
add constraint message_ai_analysis_ai_interaction_tenant_fkey
foreign key (ai_interaction_id, organization_id)
references public.ai_interactions(id, organization_id) on delete set null (ai_interaction_id);

alter table public.ai_interactions
add constraint ai_interactions_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete set null (conversation_id);

alter table public.ai_interactions
add constraint ai_interactions_message_tenant_fkey
foreign key (message_id, organization_id)
references public.messages(id, organization_id) on delete set null (message_id);

alter table public.ai_feedback
add constraint ai_feedback_ai_interaction_tenant_fkey
foreign key (ai_interaction_id, organization_id)
references public.ai_interactions(id, organization_id) on delete cascade;

alter table public.ai_feedback
add constraint ai_feedback_message_tenant_fkey
foreign key (message_id, organization_id)
references public.messages(id, organization_id) on delete set null (message_id);

alter table public.ai_feedback
add constraint ai_feedback_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete set null (conversation_id);

alter table public.conversion_events
add constraint conversion_events_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete set null (customer_id);

alter table public.conversion_events
add constraint conversion_events_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete set null (conversation_id);

alter table public.conversion_events
add constraint conversion_events_message_tenant_fkey
foreign key (message_id, organization_id)
references public.messages(id, organization_id) on delete set null (message_id);

alter table public.conversion_events
add constraint conversion_events_product_tenant_fkey
foreign key (product_id, organization_id)
references public.products(id, organization_id) on delete set null (product_id);

alter table public.automation_events
add constraint automation_events_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete set null (customer_id);

alter table public.automation_events
add constraint automation_events_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete set null (conversation_id);

alter table public.automation_events
add constraint automation_events_message_tenant_fkey
foreign key (message_id, organization_id)
references public.messages(id, organization_id) on delete set null (message_id);

create or replace function public.is_org_member(target_organization_id uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.memberships m
    where m.organization_id = target_organization_id
      and m.user_id = auth.uid()
      and m.status = 'active'
  );
$$;

revoke all on function public.is_org_member(uuid) from public;
grant execute on function public.is_org_member(uuid) to authenticated;

create trigger set_organizations_updated_at
before update on public.organizations
for each row execute function public.set_updated_at();

create trigger set_users_updated_at
before update on public.users
for each row execute function public.set_updated_at();

create trigger set_memberships_updated_at
before update on public.memberships
for each row execute function public.set_updated_at();

create trigger set_customers_updated_at
before update on public.customers
for each row execute function public.set_updated_at();

create trigger set_conversations_updated_at
before update on public.conversations
for each row execute function public.set_updated_at();

create trigger set_products_updated_at
before update on public.products
for each row execute function public.set_updated_at();

create trigger set_faq_entries_updated_at
before update on public.faq_entries
for each row execute function public.set_updated_at();

create trigger set_faq_entries_normalized_question
before insert or update of question on public.faq_entries
for each row execute function public.set_faq_normalized_question();

create trigger set_organization_usage_daily_updated_at
before update on public.organization_usage_daily
for each row execute function public.set_updated_at();

create trigger set_automation_events_updated_at
before update on public.automation_events
for each row execute function public.set_updated_at();

create index idx_memberships_user_org_status on public.memberships(user_id, organization_id, status);
create index idx_memberships_org_role_status on public.memberships(organization_id, role, status);

create index idx_customers_org_status_stage on public.customers(organization_id, status, purchase_stage);
create index idx_customers_org_lead_score on public.customers(organization_id, lead_score desc);
create index idx_customers_org_ltv on public.customers(organization_id, lifetime_value_amount desc);
create index idx_customers_org_last_engaged on public.customers(organization_id, last_engaged_at desc);
create unique index uq_customers_org_whatsapp_user_id
on public.customers(organization_id, whatsapp_user_id)
where whatsapp_user_id is not null;
create unique index uq_customers_org_whatsapp_phone_number
on public.customers(organization_id, whatsapp_phone_number)
where whatsapp_phone_number is not null;
create unique index uq_customers_org_instagram_user_id
on public.customers(organization_id, instagram_user_id)
where instagram_user_id is not null;
create unique index uq_customers_org_instagram_username
on public.customers(organization_id, instagram_username)
where instagram_username is not null;

create index idx_conversations_org_status_updated on public.conversations(organization_id, status, updated_at desc);
create index idx_conversations_org_channel_status on public.conversations(organization_id, channel, status);
create index idx_conversations_customer_updated on public.conversations(customer_id, updated_at desc);
create index idx_conversations_handoff on public.conversations(organization_id, handoff_status, priority, updated_at desc);
create unique index uq_conversations_external_id
on public.conversations(organization_id, channel, external_conversation_id)
where external_conversation_id is not null;

create index idx_messages_org_created on public.messages(organization_id, created_at desc);
create index idx_messages_conversation_created on public.messages(conversation_id, created_at desc);
create index idx_messages_customer_created on public.messages(customer_id, created_at desc);
create index idx_messages_org_channel_status on public.messages(organization_id, channel, status);
create unique index uq_messages_external_message_id
on public.messages(organization_id, channel, external_message_id)
where external_message_id is not null;
create unique index uq_messages_external_event_id
on public.messages(organization_id, channel, external_event_id)
where external_event_id is not null;
create unique index uq_messages_webhook_delivery_id
on public.messages(organization_id, channel, webhook_delivery_id)
where webhook_delivery_id is not null;

create index idx_products_org_status_category on public.products(organization_id, status, category);
create index idx_products_org_sku on public.products(organization_id, sku);
create index idx_products_org_inventory on public.products(organization_id, status, inventory_quantity);
create unique index uq_products_org_normalized_name
on public.products(organization_id, normalized_name);
create unique index uq_products_org_sku
on public.products(organization_id, sku)
where sku is not null;

create index idx_faq_entries_org_status_category on public.faq_entries(organization_id, status, category);
create unique index uq_faq_entries_org_normalized_question
on public.faq_entries(organization_id, normalized_question);

create index idx_ai_interactions_org_created on public.ai_interactions(organization_id, created_at desc);
create index idx_ai_interactions_conversation_created on public.ai_interactions(conversation_id, created_at desc);
create index idx_ai_interactions_message on public.ai_interactions(message_id);
create index idx_ai_interactions_org_model_created on public.ai_interactions(organization_id, model, created_at desc);
create unique index uq_ai_interactions_request_id
on public.ai_interactions(organization_id, provider, request_id)
where request_id is not null;

create index idx_message_ai_analysis_org_stage on public.message_ai_analysis(organization_id, purchase_stage, analyzed_at desc);
create index idx_message_ai_analysis_org_intent on public.message_ai_analysis(organization_id, intent, analyzed_at desc);
create index idx_message_ai_analysis_conversation on public.message_ai_analysis(conversation_id, analyzed_at desc);

create index idx_ai_feedback_org_created on public.ai_feedback(organization_id, created_at desc);
create index idx_ai_feedback_interaction on public.ai_feedback(ai_interaction_id);
create index idx_ai_feedback_message on public.ai_feedback(message_id);

create index idx_conversion_events_org_type_time on public.conversion_events(organization_id, event_type, occurred_at desc);
create index idx_conversion_events_customer_time on public.conversion_events(customer_id, occurred_at desc);
create index idx_conversion_events_conversation_time on public.conversion_events(conversation_id, occurred_at desc);
create index idx_conversion_events_product_time on public.conversion_events(product_id, occurred_at desc);
create unique index uq_conversion_events_event_key
on public.conversion_events(organization_id, event_type, event_key)
where event_key is not null;

create index idx_usage_daily_org_date on public.organization_usage_daily(organization_id, usage_date desc);
create index idx_usage_daily_date on public.organization_usage_daily(usage_date desc);

create index idx_automation_events_org_status_scheduled on public.automation_events(organization_id, status, scheduled_for);
create index idx_automation_events_customer_created on public.automation_events(customer_id, created_at desc);
create index idx_automation_events_conversation_created on public.automation_events(conversation_id, created_at desc);
create unique index uq_automation_events_idempotency_key
on public.automation_events(organization_id, automation_key, idempotency_key)
where idempotency_key is not null;

alter table public.organizations enable row level security;
alter table public.users enable row level security;
alter table public.memberships enable row level security;
alter table public.customers enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.products enable row level security;
alter table public.faq_entries enable row level security;
alter table public.message_ai_analysis enable row level security;
alter table public.ai_interactions enable row level security;
alter table public.ai_feedback enable row level security;
alter table public.conversion_events enable row level security;
alter table public.organization_usage_daily enable row level security;
alter table public.automation_events enable row level security;

create policy "users can read own profile"
on public.users for select
using (id = auth.uid());

create policy "users can update own profile"
on public.users for update
using (id = auth.uid())
with check (id = auth.uid());

create policy "members can read organizations"
on public.organizations for select
using (public.is_org_member(id));

create policy "members can read memberships"
on public.memberships for select
using (public.is_org_member(organization_id));

create policy "members can read customers"
on public.customers for select
using (public.is_org_member(organization_id));

create policy "members can read conversations"
on public.conversations for select
using (public.is_org_member(organization_id));

create policy "members can read messages"
on public.messages for select
using (public.is_org_member(organization_id));

create policy "members can read products"
on public.products for select
using (public.is_org_member(organization_id));

create policy "members can read faq entries"
on public.faq_entries for select
using (public.is_org_member(organization_id));

create policy "members can read message ai analysis"
on public.message_ai_analysis for select
using (public.is_org_member(organization_id));

create policy "members can read ai interactions"
on public.ai_interactions for select
using (public.is_org_member(organization_id));

create policy "members can read ai feedback"
on public.ai_feedback for select
using (public.is_org_member(organization_id));

create policy "members can read conversion events"
on public.conversion_events for select
using (public.is_org_member(organization_id));

create policy "members can read organization usage daily"
on public.organization_usage_daily for select
using (public.is_org_member(organization_id));

create policy "members can read automation events"
on public.automation_events for select
using (public.is_org_member(organization_id));

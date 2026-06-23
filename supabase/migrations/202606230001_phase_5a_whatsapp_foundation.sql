create table public.whatsapp_accounts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  phone_number_id text not null,
  whatsapp_business_account_id text,
  display_phone_number text,
  status text not null default 'pending',
  verify_token_hash text,
  access_token_secret_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint whatsapp_accounts_phone_number_id_not_blank check (btrim(phone_number_id) <> ''),
  constraint whatsapp_accounts_status_valid check (status in ('active', 'disabled', 'pending', 'revoked'))
);

alter table public.whatsapp_accounts
add constraint whatsapp_accounts_id_organization_id_unique unique (id, organization_id);

create trigger set_whatsapp_accounts_updated_at
before update on public.whatsapp_accounts
for each row execute function public.set_updated_at();

create index idx_whatsapp_accounts_org
on public.whatsapp_accounts(organization_id);

create index idx_whatsapp_accounts_org_status
on public.whatsapp_accounts(organization_id, status);

create index idx_whatsapp_accounts_phone_number_id
on public.whatsapp_accounts(phone_number_id);

create index idx_whatsapp_accounts_waba
on public.whatsapp_accounts(whatsapp_business_account_id)
where whatsapp_business_account_id is not null;

create unique index uq_whatsapp_accounts_active_phone_number_id
on public.whatsapp_accounts(phone_number_id)
where status = 'active';

create table public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_type text not null,
  delivery_id text,
  external_event_id text,
  organization_id uuid references public.organizations(id) on delete cascade,
  account_id uuid references public.whatsapp_accounts(id) on delete set null,
  phone_number_id text,
  status text not null default 'received',
  signature_valid boolean,
  resolved boolean not null default false,
  error_code text,
  error_message text,
  payload_hash text,
  payload jsonb,
  metadata jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint webhook_events_provider_not_blank check (btrim(provider) <> ''),
  constraint webhook_events_provider_normalized check (provider = lower(provider)),
  constraint webhook_events_event_type_not_blank check (btrim(event_type) <> ''),
  constraint webhook_events_status_valid check (
    status in ('received', 'processed', 'duplicate', 'ignored', 'failed', 'unresolved')
  ),
  constraint webhook_events_resolved_requires_organization check (
    resolved = false or organization_id is not null
  ),
  constraint webhook_events_account_requires_organization check (
    account_id is null or organization_id is not null
  )
);

alter table public.webhook_events
add constraint webhook_events_account_organization_fkey
foreign key (account_id, organization_id)
references public.whatsapp_accounts(id, organization_id) on delete set null (account_id);

create unique index uq_webhook_events_provider_delivery_id
on public.webhook_events(provider, delivery_id)
where delivery_id is not null;

create unique index uq_webhook_events_provider_external_event_id
on public.webhook_events(provider, external_event_id)
where external_event_id is not null;

create index idx_webhook_events_unresolved
on public.webhook_events(provider, received_at desc)
where resolved = false;

create index idx_webhook_events_org_received
on public.webhook_events(organization_id, received_at desc)
where organization_id is not null;

create index idx_webhook_events_account_received
on public.webhook_events(account_id, received_at desc)
where account_id is not null;

create index idx_webhook_events_phone_number_received
on public.webhook_events(phone_number_id, received_at desc)
where phone_number_id is not null;

alter table public.whatsapp_accounts enable row level security;
alter table public.webhook_events enable row level security;

create policy "members can read whatsapp accounts"
on public.whatsapp_accounts for select
using (public.is_org_member(organization_id));

create policy "members can read resolved webhook events"
on public.webhook_events for select
using (organization_id is not null and public.is_org_member(organization_id));

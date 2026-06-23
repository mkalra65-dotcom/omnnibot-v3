create table public.ai_draft_reviews (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  customer_id uuid references public.customers(id) on delete set null,
  source_message_id uuid references public.messages(id) on delete set null,
  ai_interaction_id uuid references public.ai_interactions(id) on delete set null,
  draft_text text not null,
  edited_text text,
  status text not null default 'pending',
  approved_by_membership_id uuid references public.memberships(id) on delete set null,
  rejected_by_membership_id uuid references public.memberships(id) on delete set null,
  approved_at timestamptz,
  rejected_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ai_draft_reviews_draft_text_not_blank check (btrim(draft_text) <> ''),
  constraint ai_draft_reviews_edited_text_not_blank check (edited_text is null or btrim(edited_text) <> ''),
  constraint ai_draft_reviews_status_valid check (
    status in ('pending', 'approved', 'edited', 'rejected', 'ready_to_send', 'sent')
  ),
  constraint ai_draft_reviews_approved_fields_consistent check (
    (status in ('approved', 'edited', 'ready_to_send', 'sent') and approved_by_membership_id is not null and approved_at is not null)
    or (status not in ('approved', 'edited', 'ready_to_send', 'sent'))
  ),
  constraint ai_draft_reviews_rejected_fields_consistent check (
    (status = 'rejected' and rejected_by_membership_id is not null and rejected_at is not null)
    or (status <> 'rejected')
  )
);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_id_organization_id_unique unique (id, organization_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_conversation_tenant_fkey
foreign key (conversation_id, organization_id)
references public.conversations(id, organization_id) on delete cascade;

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_customer_tenant_fkey
foreign key (customer_id, organization_id)
references public.customers(id, organization_id) on delete set null (customer_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_source_message_tenant_fkey
foreign key (source_message_id, organization_id)
references public.messages(id, organization_id) on delete set null (source_message_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_ai_interaction_tenant_fkey
foreign key (ai_interaction_id, organization_id)
references public.ai_interactions(id, organization_id) on delete set null (ai_interaction_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_approved_membership_tenant_fkey
foreign key (approved_by_membership_id, organization_id)
references public.memberships(id, organization_id) on delete set null (approved_by_membership_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_rejected_membership_tenant_fkey
foreign key (rejected_by_membership_id, organization_id)
references public.memberships(id, organization_id) on delete set null (rejected_by_membership_id);

create trigger set_ai_draft_reviews_updated_at
before update on public.ai_draft_reviews
for each row execute function public.set_updated_at();

create index idx_ai_draft_reviews_org_status_created
on public.ai_draft_reviews(organization_id, status, created_at desc);

create index idx_ai_draft_reviews_conversation_status_created
on public.ai_draft_reviews(organization_id, conversation_id, status, created_at desc);

create index idx_ai_draft_reviews_customer_created
on public.ai_draft_reviews(customer_id, created_at desc)
where customer_id is not null;

create index idx_ai_draft_reviews_ai_interaction
on public.ai_draft_reviews(ai_interaction_id)
where ai_interaction_id is not null;

alter table public.ai_draft_reviews enable row level security;

create policy "members can read ai draft reviews"
on public.ai_draft_reviews for select
using (public.is_org_member(organization_id));

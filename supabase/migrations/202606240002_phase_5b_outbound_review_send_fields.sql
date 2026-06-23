alter table public.ai_draft_reviews
add column sent_message_id uuid,
add column sent_by_membership_id uuid,
add column sent_at timestamptz,
add column send_idempotency_key text,
add column provider_response jsonb not null default '{}'::jsonb,
add column send_error_code text,
add column send_error_message text;

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_sent_message_tenant_fkey
foreign key (sent_message_id, organization_id)
references public.messages(id, organization_id) on delete set null (sent_message_id);

alter table public.ai_draft_reviews
add constraint ai_draft_reviews_sent_membership_tenant_fkey
foreign key (sent_by_membership_id, organization_id)
references public.memberships(id, organization_id) on delete set null (sent_by_membership_id);

create unique index uq_ai_draft_reviews_send_idempotency
on public.ai_draft_reviews(organization_id, send_idempotency_key)
where send_idempotency_key is not null;

create unique index uq_ai_draft_reviews_sent_message
on public.ai_draft_reviews(organization_id, sent_message_id)
where sent_message_id is not null;

create index idx_ai_draft_reviews_org_sent_at
on public.ai_draft_reviews(organization_id, sent_at desc)
where sent_at is not null;

create index if not exists idx_ai_draft_reviews_org_status_created
on public.ai_draft_reviews(organization_id, status, created_at desc);

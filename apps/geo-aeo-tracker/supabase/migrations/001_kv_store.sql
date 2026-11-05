-- geo-aeo-tracker key-value store
-- Mirrors the IndexedDB key-value model used by lib/client/sovereign-store.ts
-- so existing save/load call sites don't need to change.
--
-- This table is written to by the Next.js API route (/api/state) using the
-- Supabase service-role key on the server. The anon key is never used by
-- the app, so RLS is effectively bypassed. We still leave RLS ON as a
-- safety net in case the anon key is ever exposed.

create table if not exists public.kv_store (
  key         text primary key,
  value       jsonb not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists kv_store_updated_at_idx
  on public.kv_store (updated_at desc);

-- Touch updated_at on any update
create or replace function public.kv_store_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists kv_store_touch_updated_at on public.kv_store;
create trigger kv_store_touch_updated_at
  before update on public.kv_store
  for each row execute function public.kv_store_touch_updated_at();

-- Lock down to service-role only. The app accesses this table exclusively
-- from the Next.js server (service role), so no anon/public access needed.
alter table public.kv_store enable row level security;

-- No policies defined => anon/authenticated users cannot read or write.
-- service_role bypasses RLS automatically.

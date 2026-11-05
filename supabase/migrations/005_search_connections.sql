-- Provider credentials are encrypted by the application before storage.
create table if not exists public.geo_search_connections (
  org_id bigint not null references public.geo_organizations(id) on delete cascade,
  domain text not null,
  provider text not null check (provider in ('google', 'bing')),
  property_id text not null,
  encrypted_refresh_token text not null,
  status text not null default 'connected',
  last_synced_at timestamptz,
  last_result_json text not null default '{}',
  primary key (org_id, domain, provider)
);
alter table public.geo_search_connections enable row level security;

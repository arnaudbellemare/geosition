-- Access tokens are encrypted before being written; service role only.
create table if not exists public.geo_vercel_connections (
  org_id bigint not null references public.geo_organizations(id) on delete cascade,
  domain text not null,
  project_id text not null,
  team_id text not null,
  encrypted_token text not null,
  primary key (org_id, domain)
);
alter table public.geo_vercel_connections enable row level security;

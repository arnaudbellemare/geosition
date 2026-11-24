create table if not exists public.geo_mcp_workspace_grants (
  issuer text not null,
  subject text not null,
  client_id text not null,
  user_id bigint not null,
  workspace_id bigint not null,
  permissions text[] not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  primary key (issuer, subject, client_id, workspace_id),
  constraint geo_mcp_grants_membership_fk foreign key (user_id, workspace_id)
    references public.geo_memberships(user_id, org_id) on delete cascade,
  constraint geo_mcp_grants_permissions_check check (
    cardinality(permissions) > 0 and permissions <@ array['setup:read', 'setup:write']::text[]
  )
);

create index if not exists geo_mcp_grants_membership_idx
  on public.geo_mcp_workspace_grants (user_id, workspace_id);

alter table public.geo_mcp_workspace_grants enable row level security;
revoke all on table public.geo_mcp_workspace_grants from public, anon, authenticated;
grant select, insert, update, delete on table public.geo_mcp_workspace_grants to service_role;

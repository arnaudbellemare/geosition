-- Workspace invitation redemption and active session workspace.
alter table public.geo_sessions add column if not exists org_id bigint references public.geo_organizations(id) on delete set null;
create table if not exists public.geo_workspace_invitations (
  token_hash text primary key,
  org_id bigint not null references public.geo_organizations(id) on delete cascade,
  email text not null,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);
alter table public.geo_workspace_invitations enable row level security;
create or replace function public.geo_accept_workspace_invitation(p_token_hash text, p_user_id bigint, p_session_token text)
returns boolean language plpgsql security invoker set search_path = public as $$
declare invited_org bigint;
begin
  select i.org_id into invited_org from geo_workspace_invitations i
    join geo_platform_users u on u.email=i.email
    join geo_sessions s on s.user_id=u.id
    where i.token_hash=p_token_hash and i.used_at is null and i.expires_at > now()
      and u.id=p_user_id and s.token=p_session_token and s.expires_at > now()
    for update of i;
  if invited_org is null then return false; end if;
  insert into geo_memberships(user_id,org_id,role) values(p_user_id,invited_org,'member') on conflict(user_id,org_id) do nothing;
  update geo_workspace_invitations set used_at=now() where token_hash=p_token_hash;
  update geo_sessions set org_id=invited_org where token=p_session_token and user_id=p_user_id;
  return true;
end $$;
revoke all on function public.geo_accept_workspace_invitation(text,bigint,text) from public, anon, authenticated;
grant execute on function public.geo_accept_workspace_invitation(text,bigint,text) to service_role;

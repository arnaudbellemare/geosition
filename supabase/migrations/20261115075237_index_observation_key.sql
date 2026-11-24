alter table public.geo_agent_usage_events add column if not exists observation_key text;

create unique index if not exists geo_agent_usage_observation_key
  on public.geo_agent_usage_events (org_id, domain, source_type, observation_key);

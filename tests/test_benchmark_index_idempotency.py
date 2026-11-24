from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


def test_replayed_answers_are_counted_once_but_distinct_observations_remain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    org1 = service.register(email="first@example.test", password="password123", org_name="First")["organization"]["org_id"]
    org2 = service.register(email="second@example.test", password="password123", org_name="Second")["organization"]["org_id"]
    row = {"provider": "chatgpt", "model": "test", "prompt": "Compare", "answer_text": "A" * 1100,
           "citation_urls": ["https://example.com/"], "collected_at": "2026-11-15T01:00:00Z"}
    def ingest(org, answer):
        return service._record_benchmark_telemetry(org, domain="example.com", answers=[answer], benchmark_run_id=1)

    assert len(ingest(org1, row)) == 1
    assert len(ingest(org1, row)) == 0
    assert len(ingest(org2, row)) == 1
    assert len(ingest(org1, {**row, "answer_text": row["answer_text"] + "different"})) == 1
    assert len(ingest(org1, {**row, "collected_at": "2026-11-15T02:00:00Z"})) == 1
    assert store.index_summary(org1, domain="example.com").total_events == 3
    assert store.index_summary(org2, domain="example.com").total_events == 1


def test_supabase_conflict_is_ignored_in_the_owning_workspace():
    from geo_optimizer.saas.supabase_store import SupabasePlatformStore

    store = SupabasePlatformStore.__new__(SupabasePlatformStore)
    calls = []
    def request(method, table, **kwargs):
        calls.append((method, table, kwargs))
        return []
    store._request = request
    result = store.record_agent_usage_event(3, domain="example.com", source_type="benchmark",
                                            observation_key="obs_abc", skip_existing=True)
    assert result is None
    method, table, kwargs = calls[0]
    assert method == "POST" and table == "geo_agent_usage_events"
    assert kwargs["params"]["on_conflict"] == "org_id,domain,source_type,observation_key"
    assert kwargs["json_body"]["org_id"] == 3
    assert "resolution=ignore-duplicates" in kwargs["prefer"]

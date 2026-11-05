"""Tests for hybrid answer collection pipeline."""

from __future__ import annotations

from pathlib import Path

from geo_optimizer.core.collection.normalize import (
    batch_from_dict,
    batch_to_benchmark_answers,
    load_canonical_batch,
    write_canonical_batch,
)
from geo_optimizer.core.collection.store import CollectionArtifactStore
from geo_optimizer.core.collection.tracker_bridge import (
    from_brightdata_scrape,
    from_bulk_analysis_item,
    from_grounding_result,
)
from geo_optimizer.models.results.collection import CollectedAnswer, CollectedAnswerBatch, CollectedCitation


def test_canonical_roundtrip(tmp_path):
    """Canonical batch serializes and loads for benchmark ingestion."""
    batch = CollectedAnswerBatch(
        schema_version="1.0",
        target_domain="velora.example",
        collection_run_id="test-run",
        answers=[
            CollectedAnswer(
                prompt_id="p1",
                query_text="Best condo manager?",
                query_class="recommendation",
                provider="perplexity",
                surface="perplexity_sonar",
                model="sonar",
                answer_text="See https://velora.example and https://rivala.example.",
                citations=[
                    CollectedCitation(url="https://velora.example", domain="velora.example", position=1),
                ],
                collection_mode="api",
                parse_confidence=0.9,
            )
        ],
    )
    path = tmp_path / "canonical.json"
    write_canonical_batch(path, batch)
    loaded = load_canonical_batch(path)
    rows = batch_to_benchmark_answers(loaded)
    assert rows[0]["prompt"] == "Best condo manager?"
    assert rows[0]["task"] == "recommendation"
    assert rows[0]["citation_urls"][0].startswith("https://velora.example")


def test_legacy_answers_upgrade():
    """Legacy benchmark answers.json upgrades to canonical rows."""
    payload = {
        "answers": [
            {
                "prompt": "Legacy prompt",
                "answer_text": "Answer with https://example.com",
                "provider": "manual",
                "task": "discovery",
            }
        ]
    }
    batch = batch_from_dict(payload)
    assert len(batch.answers) == 1
    assert batch.answers[0].query_text == "Legacy prompt"


def test_completed_imported_answer_remains_usable():
    batch = batch_from_dict({"answers": [{"prompt": "Question", "answer_text": "An answer", "status": "done"}]})
    assert len(batch_to_benchmark_answers(batch)) == 1


def test_tracker_bridge_scrape():
    """Bright Data scrape shape normalizes to canonical answer."""
    raw = {
        "provider": "google_ai",
        "prompt": "best tools",
        "answer": "Try https://velora.example",
        "sources": ["https://velora.example", "https://rivala.example"],
        "createdAt": "2026-06-03T12:00:00+00:00",
    }
    answer = from_brightdata_scrape(raw, prompt_id="p1")
    assert answer.collection_mode == "browser"
    assert len(answer.citations) == 2
    assert answer.parse_confidence >= 0.8


def test_tracker_bridge_bulk_item():
    """Bulk analysis item expands to grounding + platform answers."""
    item = {
        "input": {"url": "https://velora.example", "keyword": "condo manager"},
        "grounding": {
            "query": "condo manager",
            "answer": "Grounded answer",
            "chunks": [{"uri": "https://velora.example", "title": "velora.example"}],
            "supports": [],
            "searchQueries": [],
            "targetUrlFound": True,
            "targetUrlChunkIndices": [0],
            "targetSnippets": [],
            "totalGroundingWords": 10,
            "targetGroundingWords": 5,
            "selectionRate": 0.5,
        },
        "platforms": [
            {
                "platform": "perplexity",
                "status": "done",
                "answer": "Perplexity answer",
                "citations": [{"url": "https://rivala.example", "domain": "rivala.example", "title": "Rival"}],
            }
        ],
    }
    answers = from_bulk_analysis_item(item)
    assert len(answers) >= 2
    providers = {a.provider for a in answers}
    assert "gemini" in providers or "perplexity" in providers


def test_grounding_bridge():
    """Gemini grounding export maps citations with positions."""
    raw = {
        "query": "test",
        "answer": "Answer text",
        "chunks": [{"uri": "https://a.example", "title": "A"}],
    }
    answer = from_grounding_result(raw)
    assert answer.collection_mode == "api"
    assert answer.citations[0].url == "https://a.example"


def test_collection_artifact_store_sanitizes_prompt_id_paths(tmp_path):
    store = CollectionArtifactStore(base_dir=tmp_path, org_slug="test")

    rel = store.save_raw(
        "../run",
        provider="manual/../../x",
        prompt_id="../../escape",
        payload={"ok": True},
    )

    saved = tmp_path / rel
    assert saved.is_file()
    assert saved.resolve().is_relative_to(tmp_path.resolve())
    assert ".." not in Path(rel).parts

"""Behavioral coverage for paired memory/search collection, evidence, and metrics."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock, patch

import pytest
import requests
from click.testing import CliRunner

from geo_optimizer.cli.experiment_cmd import experiment_group
from geo_optimizer.cli.experiment_formatter import render_memory_search_html
from geo_optimizer.core.benchmark.memory_search import (
    build_memory_search_report,
    compare_memory_search_waves,
    observe_brand,
)
from geo_optimizer.core.benchmark.runner import load_benchmark_run_result, run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.collection.adapters.gemini_grounding import GeminiGroundingAdapter
from geo_optimizer.core.collection.experiments import collect_experiment, content_hash, create_experiment
from geo_optimizer.core.collection.normalize import (
    batch_from_dict,
    batch_to_benchmark_answers,
    batch_to_dict,
    export_benchmark_answers_file,
    load_canonical_batch,
    write_canonical_batch,
)
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import CollectionArtifactStore
from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.collection import (
    AnswerProvenance,
    CitationSupport,
    CollectedAnswer,
    CollectedCitation,
    ExperimentBrand,
    PromptSpec,
)


def _experiment(repetitions=1, prompts=2, **kwargs):
    return create_experiment(
        target=ExperimentBrand(name="Acme", domain="acme.example", aliases=["Acme Cloud"]),
        competitors=[ExperimentBrand(name="Rival", domain="rival.example")],
        prompts=[
            PromptSpec(prompt_id=f"p{i}", query_text=f"Which service helps with task {i}?") for i in range(prompts)
        ],
        model="gemini-2.5-flash",
        repetitions=repetitions,
        **kwargs,
    )


def _raw(text="Use Acme.", *, search=False, supported=False, version="gemini-2.5-flash-001"):
    result = {
        "modelVersion": version,
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"totalTokenCount": 10},
    }
    if search:
        metadata = {
            "webSearchQueries": ["website audit services"],
            "groundingChunks": [{"web": {"uri": "https://acme.example/docs", "title": "Docs"}}],
        }
        if supported:
            metadata["groundingSupports"] = [
                {
                    "segment": {"startIndex": 0, "endIndex": len(text.encode("utf-8")), "text": text},
                    "groundingChunkIndices": [0],
                }
            ]
        result["candidates"][0]["groundingMetadata"] = metadata
    return result


def _response(raw):
    response = Mock()
    response.json.return_value = raw
    return response


def _answer(batch, condition, *, prompt_index=0, repetition=1, text="Use Acme.", supported=False, search=None):
    prompt = batch.prompts[prompt_index]
    manifest = batch.experiment
    provenance = AnswerProvenance(
        experiment_id=manifest.experiment_id,
        condition=condition,
        repetition=repetition,
        attempt_id=f"{prompt.prompt_id}-{condition}-{repetition}",
        prompt_hash=content_hash(asdict(prompt)),
        configuration_hash=manifest.configuration_hash,
        requested_model=manifest.model,
        returned_model="gemini-2.5-flash-001",
        context_isolated=True,
        search_enabled=condition == "search_enabled",
        search_used=False if condition == "unassisted" else search,
        available_tools=["googleSearch"] if condition == "search_enabled" else [],
    )
    citations = []
    if supported:
        citations = [
            CollectedCitation(
                url="https://acme.example/docs",
                evidence_type="citation",
                supports=[CitationSupport(start=0, end=len(text), text=text)],
            )
        ]
    answer = CollectedAnswer(
        prompt_id=prompt.prompt_id,
        query_text=prompt.query_text,
        provider="gemini",
        surface=manifest.surface,
        model=manifest.model,
        answer_text=text,
        provenance=provenance,
        citations=citations,
    )
    batch.answers.append(answer)
    return answer


def test_experiment_collection_isolates_controls_interleaves_and_preserves_all_raw_attempts(tmp_path):
    batch = _experiment(repetitions=2)
    store = CollectionArtifactStore(tmp_path / "artifacts")
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        # Return grounding only for actual tool-enabled calls.
        post.side_effect = lambda *a, **kw: _response(_raw(search="tools" in kw["json"], supported=True))
        result = collect_experiment(batch, artifact_store=store, output_path=tmp_path / "answers.json")
    assert get.call_count == 1 and post.call_count == 8
    bodies = [call.kwargs["json"] for call in post.call_args_list]
    assert ["tools" in body for body in bodies] == [False, True, True, False, True, False, False, True]
    for body in bodies:
        assert "Acme" not in json.dumps(body) and "Rival" not in json.dumps(body)
        assert set(body) <= {"contents", "tools", "generationConfig"}
    assert len({a.raw_response_path for a in result.answers}) == 8
    assert all((store.base_dir / a.raw_response_path).is_file() for a in result.answers)
    assert not batch.answers
    assert batch_from_dict(batch_to_dict(result)) == result
    assert result.experiment == batch.experiment


@pytest.mark.parametrize("prompt", ["Recommend ACME", "Find acme.example", "Compare Acme Cloud", "Use Rival"])
def test_experiment_rejects_brand_leakage_before_collection(prompt):
    with pytest.raises(ValueError, match="tracked brand"):
        create_experiment(
            target=ExperimentBrand(name="Acme", domain="acme.example", aliases=["Acme Cloud", "Rival"]),
            prompts=[PromptSpec(prompt_id="p1", query_text=prompt)],
            model="gemini-2.5-flash",
        )


def test_experiment_rejects_insufficient_request_budget_and_changed_controls():
    with pytest.raises(ValueError, match="request budget"):
        _experiment(max_requests=3)
    batch = _experiment()
    batch.prompts[0].query_text = "Changed prompt"
    with pytest.raises(ValueError, match="manifest changed"):
        build_memory_search_report(batch)


def test_experiment_capability_failure_prevents_generation(tmp_path):
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": []})
        with pytest.raises(ValueError, match="does not advertise"):
            collect_experiment(
                _experiment(), artifact_store=CollectionArtifactStore(tmp_path), output_path=tmp_path / "a.json"
            )
    post.assert_not_called()


def test_experiment_token_budget_stops_subsequent_calls_and_retains_missing_pairs(tmp_path):
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.return_value = _response(_raw())
        batch = collect_experiment(
            _experiment(max_total_tokens=5),
            artifact_store=CollectionArtifactStore(tmp_path),
            output_path=tmp_path / "answers.json",
        )
    assert post.call_count == 1
    assert len(batch.answers) == 4
    assert [a.error_code for a in batch.answers[1:]] == ["token_budget_exhausted"] * 3
    report = build_memory_search_report(batch)
    assert all(d.pair_count == 0 for cohort in report.slices for d in cohort.paired_differences)


def test_experiment_provider_failure_keeps_condition_without_exception_secrets(tmp_path):
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.side_effect = requests.HTTPError("sensitive provider exception")
        batch = collect_experiment(
            _experiment(prompts=1),
            artifact_store=CollectionArtifactStore(tmp_path),
            output_path=tmp_path / "answers.json",
        )
    assert all(a.status == "error" and a.error_code == "collection_failed" for a in batch.answers)
    assert {a.provenance.condition for a in batch.answers} == {"unassisted", "search_enabled"}
    assert "sensitive" not in json.dumps(batch_to_dict(batch))


def test_gemini_enabled_without_grounding_is_unknown_not_memory():
    adapter = GeminiGroundingAdapter(api_key="test-key")
    answer = adapter._from_raw(_raw("Acme is mentioned."), CollectionRequest(prompt=PromptSpec(query_text="Question")))
    assert answer.provenance.search_enabled is True
    assert answer.provenance.search_used is None
    assert answer.provenance.condition == "unknown"


def test_gemini_retrieved_chunks_are_not_automatically_citations():
    adapter = GeminiGroundingAdapter(api_key="test-key")
    answer = adapter._from_raw(_raw(search=True), CollectionRequest(prompt=PromptSpec(query_text="Question")))
    assert answer.provenance.search_used is True
    assert answer.provenance.retrieved_sources
    assert not answer.citations


def test_gemini_citation_offsets_handle_unicode_multiple_parts_and_private_thoughts():
    adapter = GeminiGroundingAdapter(api_key="test-key")
    text = "Préférez Acme."
    raw = _raw(text, search=True, supported=True)
    raw["candidates"][0]["content"]["parts"] = [
        {"text": "private", "thought": True},
        {"text": "Intro. "},
        {"text": text},
    ]
    raw["candidates"][0]["groundingMetadata"]["groundingSupports"][0]["segment"]["partIndex"] = 2
    answer = adapter._from_raw(raw, CollectionRequest(prompt=PromptSpec(query_text="Question")))
    support = answer.citations[0].supports[0]
    assert answer.answer_text[support.start : support.end] == text
    assert "private" not in answer.answer_text
    assert support.start == len("Intro. ")


@pytest.mark.parametrize(
    "raw,status",
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "refused"),
        ({"candidates": []}, "empty"),
        ({"candidates": [{"content": {"parts": [{"text": "Acme"}]}, "finishReason": "MAX_TOKENS"}]}, "error"),
    ],
)
def test_gemini_invalid_answers_remain_outside_success_denominator(raw, status):
    answer = GeminiGroundingAdapter(api_key="test-key")._from_raw(raw, CollectionRequest(prompt=PromptSpec()))
    assert answer.status == status and not answer.answer_text


def test_memory_search_rates_use_equal_prompt_weight_and_complete_pairs():
    batch = _experiment(repetitions=2)
    _answer(batch, "unassisted", text="Other service.")
    _answer(batch, "search_enabled", search=True, supported=True)
    _answer(batch, "unassisted", repetition=2, text="Other service.")
    _answer(batch, "search_enabled", repetition=2, search=None)
    _answer(batch, "unassisted", prompt_index=1)
    _answer(batch, "search_enabled", prompt_index=1, text="Other service.", search=False)
    report = build_memory_search_report(batch)
    target = next(c for c in report.slices if c.brand == "Acme")
    memory, search = target.conditions
    assert memory.mention_rate == 50 and search.mention_rate == 50
    assert memory.valid_answers == 3 and search.valid_answers == 3
    assert search.search_use_rate == 50
    assert search.search_observed_answers == 2 and search.search_unknown_answers == 1
    assert search.search_backed_rate == 25  # p0: 1/2, p1: 0/1; equally weighted.
    assert target.paired_differences[0].delta_pp == 0
    assert target.paired_differences[0].pair_count == 3
    assert target.paired_differences[0].prompt_count == 2
    assert report.missing_attempts == 2


def test_memory_search_never_pairs_changed_model_versions_or_opaque_browser_answers():
    batch = _experiment(prompts=1)
    _answer(batch, "unassisted")
    search = _answer(batch, "search_enabled", search=True)
    search.provenance.returned_model = "new-version"
    report = build_memory_search_report(batch)
    assert all(d.pair_count == 0 for c in report.slices for d in c.paired_differences)
    search.collection_mode = "browser"
    assert build_memory_search_report(batch).unclassified_attempts == 1


def test_memory_search_unknown_legacy_records_are_not_reclassified_from_provider():
    batch = batch_from_dict({"answers": [{"prompt": "Question", "answer_text": "Acme", "provider": "gemini"}]})
    report = build_memory_search_report(batch)
    assert report.unclassified_attempts == 1 and not report.slices
    assert batch.answers[0].provenance.search_used is None


def test_memory_search_duplicate_slots_are_rejected():
    batch = _experiment()
    _answer(batch, "unassisted")
    _answer(batch, "unassisted")
    with pytest.raises(ValueError, match="Duplicate"):
        build_memory_search_report(batch)


@pytest.mark.parametrize(
    "text,mentioned,recommended",
    [
        ("Use Acme.", True, True),
        ("Acme is mentioned.", True, False),
        ("I do not recommend Acme.", True, False),
        ("Choose Acme Cloud.", True, True),
        ("Utilisez Acme.", True, True),
        ("Acmeology is a word.", False, False),
        ("Use Rival. Acme is merely listed.", True, False),
    ],
)
def test_brand_outcomes_distinguish_mentions_explicit_recommendations_and_negation(text, mentioned, recommended):
    result = observe_brand(CollectedAnswer(answer_text=text), ExperimentBrand(name="Acme", domain="acme.example"))
    assert result.mentioned is mentioned and result.recommended is recommended


def test_search_backing_requires_support_on_the_brand_not_an_unrelated_citation():
    batch = _experiment(prompts=1)
    answer = _answer(batch, "search_enabled", text="Acme is mentioned. Another fact.", search=True)
    answer.citations = [
        CollectedCitation(
            url="https://news.example/article",
            evidence_type="citation",
            supports=[CitationSupport(start=19, end=32, text="Another fact.")],
        )
    ]
    observation = observe_brand(answer, batch.experiment.target)
    assert observation.mentioned and not observation.search_backed and not observation.owned_domain_cited
    answer.citations[0].supports = [CitationSupport(start=0, end=18, text="Acme is mentioned.")]
    observation = observe_brand(answer, batch.experiment.target)
    assert observation.search_backed and not observation.owned_domain_cited


def test_experiment_benchmark_roundtrip_retains_full_manifest_and_failed_attempts(tmp_path):
    batch = _experiment(prompts=1)
    _answer(batch, "unassisted")
    _answer(batch, "search_enabled").status = "error"
    store = BenchmarkStore(tmp_path / "benchmark.db")
    with patch(
        "geo_optimizer.core.benchmark.runner.run_full_audit",
        return_value=AuditResult(url="https://acme.example", error="unavailable"),
    ):
        result = run_domain_benchmark(batch.target_domain, answers=batch_to_benchmark_answers(batch), store=store)
    loaded = load_benchmark_run_result(result.run_id, store=store)
    artifact = next(a for a in loaded.evidence_artifacts if a.artifact_type == "memory_search_experiment")
    restored = batch_from_dict(json.loads(artifact.payload))
    assert restored.experiment == batch.experiment
    assert len(restored.answers) == 2 and restored.answers[1].status == "error"
    assert restored.answers[0].provenance == batch.answers[0].provenance


def test_experiment_export_preserves_provenance_and_manifest(tmp_path):
    batch = _experiment(prompts=1)
    _answer(batch, "unassisted")
    path = tmp_path / "canonical.json"
    write_canonical_batch(path, batch)
    rows = export_benchmark_answers_file(path, tmp_path / "benchmark.json")
    assert rows[0]["collection_evidence"]["provenance"]["condition"] == "unassisted"
    assert rows[0]["experiment"]["experiment_id"] == batch.experiment.experiment_id
    assert not rows[0]["citation_urls"]  # No inference from URLs in experiment text.


def test_experiment_wave_comparison_rejects_changes_and_reports_observed_movement():
    before = _experiment(prompts=1)
    _answer(before, "unassisted", text="Other service.")
    _answer(before, "search_enabled", text="Other service.")
    after = deepcopy(before)
    after.answers[1].answer_text = "Use Acme."
    changes = compare_memory_search_waves(before, after)
    assert (
        next(c for c in changes["changes"] if c["brand"] == "Acme" and c["condition"] == "search_enabled")[
            "mention_delta_pp"
        ]
        == 100
    )
    with pytest.raises(ValueError, match="Noncomparable"):
        compare_memory_search_waves(before, _experiment(prompts=2))


def test_experiment_cli_create_run_and_report_are_reviewable_without_paid_calls(tmp_path):
    runner = CliRunner()
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps([{"prompt_id": "p1", "query_text": "Find a website audit service"}]))
    frozen, output = tmp_path / "experiment.json", tmp_path / "answers.json"
    result = runner.invoke(
        experiment_group,
        [
            "create",
            "acme.example",
            "--brand",
            "Acme",
            "--model",
            "gemini-2.5-flash",
            "--prompts-file",
            str(prompts),
            "--repetitions",
            "1",
            "--output",
            str(frozen),
        ],
    )
    assert result.exit_code == 0, result.output
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.side_effect = lambda *a, **kw: _response(_raw(search="tools" in kw["json"], supported=True))
        result = runner.invoke(experiment_group, ["run", "--experiment", str(frozen), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "answers.report" / "memory-search.html").is_file()
    with patch("requests.post") as post, patch("requests.get") as get:
        result = runner.invoke(
            experiment_group, ["report", "--input", str(output), "--output-dir", str(tmp_path / "offline")]
        )
    assert result.exit_code == 0, result.output
    post.assert_not_called()
    get.assert_not_called()
    assert "unassisted" in result.output and "search_enabled" in result.output
    assert len(load_canonical_batch(output).answers) == 2


def test_experiment_html_escapes_provider_text_and_paths():
    batch = _experiment(prompts=1)
    _answer(batch, "unassisted", text="<script>alert('Acme')</script>")
    html = render_memory_search_html(build_memory_search_report(batch))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Answer evidence" in html and "Explicit recommendation" in html


def test_experiment_manual_and_tracker_import_preserve_trials_and_evidence(tmp_path):
    from geo_optimizer.core.collection.adapters.manual import ManualFileAdapter
    from geo_optimizer.core.collection.pipeline import import_tracker_export

    batch = _experiment(prompts=1)
    _answer(batch, "unassisted")
    original = _answer(batch, "search_enabled", search=True, supported=True)
    path = tmp_path / "canonical.json"
    write_canonical_batch(path, batch)
    assert import_tracker_export(path) == batch
    adapter = ManualFileAdapter(source_path=path)
    restored = adapter.collect(CollectionRequest(prompt=batch.prompts[0], provenance=original.provenance))
    assert restored.provenance == original.provenance
    assert restored.citations == original.citations
    assert restored.surface == original.surface
    exported = tmp_path / "benchmark.json"
    export_benchmark_answers_file(path, exported)
    assert load_canonical_batch(exported) == batch
    assert import_tracker_export(exported) == batch


def test_experiment_wave_comparison_matches_missing_answers_instead_of_claiming_gain():
    before = _experiment(prompts=2)
    _answer(before, "unassisted", text="Other service.")
    _answer(before, "search_enabled", text="Other service.")
    _answer(before, "unassisted", prompt_index=1)
    _answer(before, "search_enabled", prompt_index=1)
    after = deepcopy(before)
    after.answers.pop(1)  # A missing negative observation must not increase visibility.
    result = compare_memory_search_waves(before, after)
    assert result["matched_observation_slots"] == 3
    assert result["unmatched_before"] == 1
    assert all(c["mention_delta_pp"] == 0 for c in result["changes"])


def test_experiment_requests_never_add_system_context_and_disabled_tools_are_absent():
    adapter = GeminiGroundingAdapter(api_key="test-key")
    with patch("requests.post", return_value=_response(_raw())) as post:
        answer = adapter.collect(
            CollectionRequest(
                prompt=PromptSpec(query_text="Find an audit service"),
                target_domain="secret-brand.example",
                retrieval_policy="disabled",
                generation_settings={"maxOutputTokens": 100},
            )
        )
    body = post.call_args.kwargs["json"]
    assert "tools" not in body and "systemInstruction" not in body and "cachedContent" not in body
    assert "secret-brand" not in json.dumps(body)
    assert answer.provenance.search_enabled is False and answer.provenance.search_used is False


def test_experiment_unexpected_retrieval_invalidates_unassisted_answer():
    answer = GeminiGroundingAdapter(api_key="test-key")._from_raw(
        _raw(search=True, supported=True), CollectionRequest(prompt=PromptSpec(), retrieval_policy="disabled")
    )
    assert answer.status == "error" and answer.error_code == "unexpected_retrieval"


def test_experiment_budget_with_missing_usage_stops_further_requests(tmp_path):
    raw = _raw()
    raw.pop("usageMetadata")
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.return_value = _response(raw)
        batch = collect_experiment(
            _experiment(max_total_tokens=1000),
            artifact_store=CollectionArtifactStore(tmp_path),
            output_path=tmp_path / "answers.json",
        )
    assert post.call_count == 1
    assert all(a.error_code == "token_usage_unavailable" for a in batch.answers[1:])


def test_experiment_cli_preserves_existing_output_and_failure_evidence(tmp_path):
    runner = CliRunner()
    frozen, output = tmp_path / "experiment.json", tmp_path / "answers.json"
    write_canonical_batch(frozen, _experiment(prompts=1))
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.side_effect = requests.HTTPError("credential must not escape")
        result = runner.invoke(experiment_group, ["run", "--experiment", str(frozen), "--output", str(output)])
    assert result.exit_code == 1 and "failed attempt evidence was saved" in result.output
    assert "credential must not escape" not in result.output
    assert len(load_canonical_batch(output).answers) == 2
    original = output.read_bytes()
    result = runner.invoke(experiment_group, ["run", "--experiment", str(frozen), "--output", str(output)])
    assert result.exit_code == 1 and "Output already exists" in result.output
    assert output.read_bytes() == original


@pytest.mark.parametrize(
    "text", ["Use Rival instead of Acme.", "I recommend Rival over Acme.", "Try Rival, which integrates with Acme."]
)
def test_explicit_recommendation_does_not_promote_every_brand_in_the_sentence(text):
    observation = observe_brand(CollectedAnswer(answer_text=text), ExperimentBrand(name="Acme", domain="acme.example"))
    assert observation.mentioned and not observation.recommended


def test_experiment_export_retains_manifest_when_every_attempt_failed(tmp_path):
    batch = _experiment(prompts=1)
    _answer(batch, "unassisted").status = "error"
    _answer(batch, "search_enabled").status = "refused"
    original, exported = tmp_path / "canonical.json", tmp_path / "benchmark.json"
    write_canonical_batch(original, batch)
    assert export_benchmark_answers_file(original, exported) == []
    restored = load_canonical_batch(exported)
    assert restored.experiment == batch.experiment
    assert [a.status for a in restored.answers] == ["error", "refused"]


def test_experiment_report_cannot_overwrite_canonical_evidence(tmp_path):
    source = tmp_path / "memory-search.json"
    write_canonical_batch(source, _experiment(prompts=1))
    original = source.read_bytes()
    result = CliRunner().invoke(experiment_group, ["report", "--input", str(source), "--output-dir", str(tmp_path)])
    assert result.exit_code == 1 and "would overwrite canonical evidence" in result.output
    assert source.read_bytes() == original


def test_experiment_collection_cannot_write_report_over_canonical_evidence(tmp_path):
    source, output = tmp_path / "frozen.json", tmp_path / "memory-search.json"
    write_canonical_batch(source, _experiment(prompts=1))
    with patch("requests.post") as post, patch("requests.get") as get:
        result = CliRunner().invoke(
            experiment_group,
            ["run", "--experiment", str(source), "--output", str(output), "--report-dir", str(tmp_path)],
        )
    assert result.exit_code == 1 and "would overwrite canonical evidence" in result.output
    post.assert_not_called()
    get.assert_not_called()


def test_experiment_cli_missing_model_version_reports_unknown_provenance(tmp_path):
    frozen, output = tmp_path / "experiment.json", tmp_path / "answers.json"
    write_canonical_batch(frozen, _experiment(prompts=1))
    raw = _raw()
    raw.pop("modelVersion")
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
        patch("requests.get") as get,
        patch("requests.post") as post,
    ):
        get.return_value = _response({"supportedGenerationMethods": ["generateContent"]})
        post.return_value = _response(raw)
        result = CliRunner().invoke(experiment_group, ["run", "--experiment", str(frozen), "--output", str(output)])
    assert result.exit_code == 1 and "unknown provenance" in result.output
    assert build_memory_search_report(load_canonical_batch(output)).unclassified_attempts == 2

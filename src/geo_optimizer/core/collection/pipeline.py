"""Two-stage collection pipeline: collect raw → normalize canonical answers.json."""

from __future__ import annotations

import json
from pathlib import Path

from geo_optimizer.core.collection.adapters import get_adapter
from geo_optimizer.core.collection.normalize import (
    batch_from_dict,
    write_canonical_batch,
)
from geo_optimizer.core.collection.store import CollectionArtifactStore, new_collection_run_id
from geo_optimizer.core.collection.tracker_bridge import (
    from_brightdata_scrape,
    from_bulk_analysis_item,
    from_grounding_result,
    from_platform_result,
)
from geo_optimizer.models.results.collection import CollectedAnswer, CollectedAnswerBatch, PromptSpec


def load_prompt_specs(path: Path) -> list[PromptSpec]:
    """Load prompt set from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("prompts", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError('Prompts file must contain a list or {"prompts": [...]}')
    specs: list[PromptSpec] = []
    for index, item in enumerate(items):
        query = str(item.get("query_text", item.get("prompt", ""))).strip()
        if not query:
            continue
        prompt_id = str(item.get("prompt_id", "")) or f"p{index + 1}"
        specs.append(
            PromptSpec(
                prompt_id=prompt_id,
                query_text=query,
                query_class=str(item.get("query_class", item.get("task", ""))),
                keyword_topic=str(item.get("keyword_topic", "")),
                persona=str(item.get("persona", "")),
                country=str(item.get("country", "")),
                language=str(item.get("language", "en")),
            )
        )
    return specs


def _save_raw_for_adapter(adapter, request, store, run_id) -> tuple[CollectedAnswer, dict | None]:
    """Collect answer and persist raw payload when adapter supports it."""

    if hasattr(adapter, "collect_with_raw"):
        answer, raw = adapter.collect_with_raw(request)
        rel = store.save_raw(run_id, provider=adapter.provider_id, prompt_id=request.prompt.prompt_id, payload=raw)
        answer.raw_response_path = rel
        return answer, raw
    answer = adapter.collect(request)
    rel = store.save_raw(
        run_id,
        provider=adapter.provider_id,
        prompt_id=request.prompt.prompt_id,
        payload={"query_text": request.prompt.query_text, "answer_text": answer.answer_text},
    )
    answer.raw_response_path = rel
    return answer, None


def collect_and_normalize(
    *,
    target_domain: str,
    prompts: list[PromptSpec],
    providers: list[str],
    country: str = "",
    device: str = "desktop",
    artifact_store: CollectionArtifactStore | None = None,
    adapter_kwargs: dict | None = None,
) -> CollectedAnswerBatch:
    """Stage 1+2: run adapters per prompt/provider, save raw, return canonical batch."""
    from geo_optimizer.core.collection.protocol import CollectionRequest

    org_slug = target_domain.strip().lower().replace(".", "-")
    store = artifact_store or CollectionArtifactStore(org_slug=org_slug)
    run_id = new_collection_run_id()
    kwargs = adapter_kwargs or {}
    answers: list[CollectedAnswer] = []

    for provider_id in providers:
        adapter = get_adapter(provider_id, **kwargs.get(provider_id, {}))
        for prompt in prompts:
            request = CollectionRequest(
                prompt=prompt,
                target_domain=target_domain,
                country=country or prompt.country,
                language=prompt.language,
                device=device,
            )
            try:
                answer, _raw = _save_raw_for_adapter(adapter, request, store, run_id)
                answers.append(answer)
            except Exception:
                answers.append(
                    CollectedAnswer(
                        prompt_id=prompt.prompt_id,
                        query_text=prompt.query_text,
                        query_class=prompt.query_class,
                        provider=adapter.provider_id,
                        surface=getattr(adapter, "surface", adapter.provider_id),
                        answer_text="",
                        collection_mode=getattr(adapter, "collection_mode", "api"),
                        parse_confidence=0.0,
                        language=request.language,
                        status="error",
                        error_code="collection_failed",
                    )
                )

    batch = CollectedAnswerBatch(
        target_domain=target_domain,
        collection_run_id=run_id,
        prompts=prompts,
        answers=answers,
    )
    canonical_path = store.base_dir / "canonical" / f"{run_id}.json"
    write_canonical_batch(canonical_path, batch)
    return batch


def normalize_raw_directory(
    raw_dir: Path,
    *,
    target_domain: str = "",
    collection_run_id: str = "",
) -> CollectedAnswerBatch:
    """Stage 2 only: normalize saved raw JSON files into canonical answers."""
    answers: list[CollectedAnswer] = []
    for path in sorted(raw_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = path.stem
        if "grounding" in name or raw.get("groundingMetadata") or raw.get("chunks"):
            answers.append(from_grounding_result(raw))
        elif raw.get("platform") and raw.get("citations") is not None:
            answers.append(from_platform_result(raw))
        elif raw.get("provider") and raw.get("answer") is not None:
            answers.append(from_brightdata_scrape(raw))
        elif raw.get("choices"):
            # OpenAI-style — minimal fallback
            text = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            answers.append(
                CollectedAnswer(
                    query_text=str(raw.get("query_text", "")),
                    provider="openai",
                    surface="openai_web",
                    answer_text=str(text),
                    collection_mode="api",
                    parse_confidence=0.7,
                )
            )
        else:
            answers.append(
                CollectedAnswer(
                    query_text=name,
                    answer_text=json.dumps(raw)[:2000],
                    provider="unknown",
                    collection_mode="api",
                    parse_confidence=0.3,
                )
            )

    return CollectedAnswerBatch(
        target_domain=target_domain,
        collection_run_id=collection_run_id or raw_dir.name,
        answers=answers,
    )


def import_tracker_export(path: Path, *, target_domain: str = "") -> CollectedAnswerBatch:
    """Import geo-aeo-tracker bulk export JSON into canonical batch."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    answers: list[CollectedAnswer] = []

    if isinstance(payload, list):
        for item in payload:
            answers.extend(from_bulk_analysis_item(item))
    elif isinstance(payload, dict):
        if "platforms" in payload or "grounding" in payload:
            answers.extend(from_bulk_analysis_item(payload))
        elif "results" in payload:
            for item in payload["results"]:
                answers.extend(from_bulk_analysis_item(item))
        else:
            batch = batch_from_dict(payload)
            return batch

    return CollectedAnswerBatch(
        target_domain=target_domain,
        answers=answers,
    )


def export_benchmark_answers_file(canonical_path: Path, output_path: Path, **kwargs) -> list[dict]:
    """Re-export from normalize module for package __init__."""
    from geo_optimizer.core.collection.normalize import export_benchmark_answers_file as _export

    return _export(canonical_path, output_path, **kwargs)

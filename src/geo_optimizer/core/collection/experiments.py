"""Freeze and collect unbranded, paired memory/search experiments."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import requests

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.core.collection.adapters.gemini_grounding import GeminiGroundingAdapter
from geo_optimizer.core.collection.normalize import write_canonical_batch
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import CollectionArtifactStore, _now_iso, new_collection_run_id
from geo_optimizer.models.config import (
    EXPERIMENT_MAX_OUTPUT_TOKENS,
    EXPERIMENT_MAX_REQUESTS,
    EXPERIMENT_REPETITIONS,
    EXPERIMENT_TEMPERATURE,
)
from geo_optimizer.models.results.collection import (
    AnswerProvenance,
    CollectedAnswer,
    CollectedAnswerBatch,
    ExperimentBrand,
    ExperimentManifest,
    PromptSpec,
)


def content_hash(value: object) -> str:
    """Stable hash of JSON-compatible experiment controls."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def brand_terms(brand: ExperimentBrand) -> list[str]:
    """Scoring identities and leakage checks share the same normalized aliases."""
    return list(dict.fromkeys(t.strip() for t in [brand.name, *brand.aliases, brand.domain] if t.strip()))


def _configuration(manifest: ExperimentManifest) -> dict:
    return {
        "provider": manifest.provider,
        "surface": manifest.surface,
        "model": manifest.model,
        "generation_settings": manifest.generation_settings,
        "system_instruction_hash": manifest.system_instruction_hash,
        "context_isolated": True,
    }


def validate_experiment(batch: CollectedAnswerBatch) -> ExperimentManifest:
    """Reject changed controls, duplicate prompts, or branded discovery prompts."""
    manifest = batch.experiment
    if not manifest or manifest.schema_version != "1.0":
        raise ValueError("A supported experiment manifest is required")
    if manifest.provider != "gemini" or manifest.surface != "gemini_generate_content" or not manifest.model.strip():
        raise ValueError("The first experiment collector requires an explicit Gemini generateContent model")
    GeminiGroundingAdapter(model=manifest.model)
    if manifest.repetitions < 1 or manifest.max_requests < 1:
        raise ValueError("Repetitions and request budget must be positive")
    if manifest.max_total_tokens is not None and manifest.max_total_tokens < 1:
        raise ValueError("Token budget must be positive")
    if not batch.prompts or any(not p.prompt_id.strip() or not p.query_text.strip() for p in batch.prompts):
        raise ValueError("Nonempty prompts and prompt IDs are required")
    if len({p.prompt_id for p in batch.prompts}) != len(batch.prompts):
        raise ValueError("Prompt IDs must be unique")
    if len({p.query_text.strip().casefold() for p in batch.prompts}) != len(batch.prompts):
        raise ValueError("Prompt text must be unique so repeated questions cannot overweight a cohort")
    if not manifest.target.name.strip() or not manifest.target.domain.strip():
        raise ValueError("Target brand name and domain are required")
    brands = [manifest.target, *manifest.competitors]
    if len({b.name.casefold() for b in brands}) != len(brands):
        raise ValueError("Brand names must be unique")
    for prompt in batch.prompts:
        folded = " ".join(prompt.query_text.casefold().split())
        for brand in brands:
            for term in brand_terms(brand):
                if " ".join(term.casefold().split()) in folded:
                    raise ValueError(f"Prompt {prompt.prompt_id} contains a tracked brand, alias, or domain")
    if manifest.prompt_set_hash != content_hash([asdict(p) for p in batch.prompts]):
        raise ValueError("Prompt manifest changed; create a new experiment")
    if manifest.system_instruction_hash != content_hash(""):
        raise ValueError("Experiments require an empty system instruction")
    settings = manifest.generation_settings
    if set(settings) != {"temperature", "maxOutputTokens"}:
        raise ValueError("Experiment settings must contain only temperature and maxOutputTokens")
    if not isinstance(settings["temperature"], (int, float)) or not 0 <= settings["temperature"] <= 2:
        raise ValueError("Temperature must be between 0 and 2")
    if type(settings["maxOutputTokens"]) is not int or settings["maxOutputTokens"] < 1:
        raise ValueError("maxOutputTokens must be a positive integer")
    if manifest.configuration_hash != content_hash(_configuration(manifest)):
        raise ValueError("Model or generation controls changed; create a new experiment")
    return manifest


def create_experiment(
    *,
    target: ExperimentBrand,
    prompts: list[PromptSpec],
    model: str,
    competitors: list[ExperimentBrand] | None = None,
    repetitions: int = EXPERIMENT_REPETITIONS,
    max_requests: int = EXPERIMENT_MAX_REQUESTS,
    max_output_tokens: int = EXPERIMENT_MAX_OUTPUT_TOKENS,
    max_total_tokens: int | None = None,
    temperature: float = EXPERIMENT_TEMPERATURE,
) -> CollectedAnswerBatch:
    """Freeze controls without sending any request or exposing scoring identities."""
    target = replace(target, domain=normalize_benchmark_domain(target.domain))
    manifest = ExperimentManifest(
        experiment_id=f"memory-search-{uuid4().hex}",
        target=deepcopy(target),
        competitors=deepcopy(competitors or []),
        model=model.strip(),
        repetitions=repetitions,
        max_requests=max_requests,
        max_total_tokens=max_total_tokens,
        generation_settings={"temperature": temperature, "maxOutputTokens": max_output_tokens},
        prompt_set_hash=content_hash([asdict(p) for p in prompts]),
        system_instruction_hash=content_hash(""),
        created_at=_now_iso(),
    )
    manifest.configuration_hash = content_hash(_configuration(manifest))
    batch = CollectedAnswerBatch(target_domain=target.domain, prompts=deepcopy(prompts), experiment=manifest)
    validate_experiment(batch)
    if len(prompts) * repetitions * 2 > max_requests:
        raise ValueError("The request budget cannot cover the complete paired experiment")
    return batch


def collect_experiment(
    batch: CollectedAnswerBatch,
    *,
    artifact_store: CollectionArtifactStore,
    output_path: Path,
) -> CollectedAnswerBatch:
    """Interleave conditions, retain every attempt, and checkpoint after each response.

    Request count and per-request output limits are hard limits. A cumulative token
    budget stops subsequent calls after provider-reported usage reaches the limit;
    the final call can cross it. Search counts are observed, not a hard spend cap.
    """
    manifest = validate_experiment(batch)
    if batch.answers or batch.collection_run_id:
        raise ValueError("This wave already has attempts; create a new wave instead of overwriting evidence")
    if len(batch.prompts) * manifest.repetitions * 2 > manifest.max_requests:
        raise ValueError("The request budget cannot cover the complete paired experiment")
    adapter = GeminiGroundingAdapter(model=manifest.model)
    capability = adapter.check_capabilities()
    result = replace(
        deepcopy(batch), collection_run_id=new_collection_run_id(), artifact_base=str(artifact_store.base_dir.resolve())
    )
    artifact_store.save_raw(result.collection_run_id, provider="gemini", prompt_id="capabilities", payload=capability)
    used_tokens = 0
    token_budget_unknown = False
    write_canonical_batch(output_path, result)
    for repetition in range(1, manifest.repetitions + 1):
        for index, prompt in enumerate(result.prompts):
            conditions = ["unassisted", "search_enabled"]
            if (repetition + index) % 2 == 0:
                conditions.reverse()
            for condition in conditions:
                attempt_id = f"{condition}-{repetition}-{uuid4().hex[:8]}"
                provenance = AnswerProvenance(
                    experiment_id=manifest.experiment_id,
                    condition=condition,
                    repetition=repetition,
                    attempt_id=attempt_id,
                    prompt_hash=content_hash(asdict(prompt)),
                    configuration_hash=manifest.configuration_hash,
                    requested_model=manifest.model,
                    context_isolated=True,
                    request_sent=False,
                    requested_language=prompt.language,
                    requested_country=prompt.country,
                    search_enabled=condition == "search_enabled",
                    available_tools=["googleSearch"] if condition == "search_enabled" else [],
                )
                request = CollectionRequest(
                    prompt=prompt,
                    language=prompt.language,
                    country=prompt.country,
                    retrieval_policy="enabled" if condition == "search_enabled" else "disabled",
                    provenance=provenance,
                    generation_settings=manifest.generation_settings,
                )
                exhausted = manifest.max_total_tokens is not None and used_tokens >= manifest.max_total_tokens
                error = "token_usage_unavailable" if token_budget_unknown else "token_budget_exhausted"
                answer = CollectedAnswer(
                    prompt_id=prompt.prompt_id,
                    query_text=prompt.query_text,
                    query_class=prompt.query_class,
                    provider="gemini",
                    surface=manifest.surface,
                    model=manifest.model,
                    language=prompt.language,
                    collected_at=_now_iso(),
                    status="error",
                    provenance=provenance,
                )
                if not exhausted and not token_budget_unknown:
                    try:
                        provenance.request_sent = True
                        answer, raw = adapter.collect_with_raw(request)
                        answer.raw_response_path = artifact_store.save_raw(
                            result.collection_run_id,
                            provider="gemini",
                            prompt_id=prompt.prompt_id,
                            attempt_id=attempt_id,
                            payload=raw,
                        )
                        tokens = answer.provenance.usage.get("totalTokenCount")
                        if tokens is not None:
                            used_tokens += tokens
                        elif manifest.max_total_tokens is not None:
                            token_budget_unknown = True
                    except (requests.RequestException, ValueError, RuntimeError):
                        # Never copy provider exception text: it can contain credentials.
                        answer.error_code = "collection_failed"
                        answer.status = "error"
                        if manifest.max_total_tokens is not None:
                            token_budget_unknown = True
                        answer.raw_response_path = artifact_store.save_raw(
                            result.collection_run_id,
                            provider="gemini",
                            prompt_id=prompt.prompt_id,
                            attempt_id=attempt_id,
                            payload={"status": "error", "error_code": answer.error_code},
                        )
                else:
                    answer.error_code = error
                result.answers.append(answer)
                write_canonical_batch(output_path, result)
    return result

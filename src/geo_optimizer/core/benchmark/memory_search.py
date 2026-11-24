"""Evidence-based memory/search outcomes; no rendering or readiness scoring."""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from statistics import mean

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.core.collection.experiments import brand_terms, content_hash, validate_experiment
from geo_optimizer.core.collection.store import _now_iso
from geo_optimizer.models.config import EXPERIMENT_BOOTSTRAP_SAMPLES
from geo_optimizer.models.results.collection import CollectedAnswer, CollectedAnswerBatch, ExperimentBrand
from geo_optimizer.models.results.experiment import (
    BrandObservation,
    ConditionMetrics,
    ExperimentSlice,
    MemorySearchReport,
    PairedDifference,
)

_RECOMMENDATION = re.compile(
    r"\b(recommend(?:ed|s)?|choose|use|try|pick|select|best (?:choice|option)|"
    r"recommand(?:e|er|ons|ez)|choisissez|utilisez|essayez|meilleur(?:e)? (?:choix|option))\b",
    re.I,
)
_NEGATION = re.compile(
    r"\b(not|never|avoid|cannot|can't|don't|doesn't|isn't|aren't|wouldn't|won't|"
    r"no recommendation|ne|pas|jamais|évitez|déconseill\w*)\b",
    re.I,
)
_CONDITIONS = ("unassisted", "search_enabled")


def _mentions(text: str, brand: ExperimentBrand) -> list[dict]:
    spans = []
    for term in brand_terms(brand):
        for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, flags=re.I):
            span = {"start": match.start(), "end": match.end(), "text": match.group()}
            if span not in spans:
                spans.append(span)
    return sorted(spans, key=lambda span: span["start"])


def observe_brand(answer: CollectedAnswer, brand: ExperimentBrand) -> BrandObservation:
    """Classify explicit recommendations conservatively with inspectable spans.

    This rule recognizes English/French recommendation verbs, not implicit praise
    or all languages. Negated sentences are excluded from positive classification.
    """
    mentions = _mentions(answer.answer_text, brand)
    recommendations = []
    names = "(?:" + "|".join(re.escape(term) for term in brand_terms(brand)) + ")"
    direct = re.compile(
        _RECOMMENDATION.pattern
        + r"(?:\s+(?:using|trying|choosing|the|tool|service|platform|provider|le|la|les|un|une|utiliser|choisir)){0,4}"
        + r"[\s:*_`]+(?<!\w)"
        + names
        + r"(?!\w)",
        re.I,
    )
    subject = re.compile(
        r"(?<!\w)" + names + r"(?!\w)\s+(?:is|would be|est|reste)\s+(?:(?:the|a|le|la|un|une)\s+)?"
        r"(?:best (?:choice|option)|recommended|meilleur(?:e)? (?:choix|option)|recommandé(?:e)?)\b",
        re.I,
    )
    for sentence in re.finditer(r"[^\n!?;]+(?:[!?;]|$)", answer.answer_text):
        # Split full stops followed by whitespace, preserving dots inside domains.
        offset = sentence.start()
        for part in re.split(r"(?<=\.)\s+", sentence.group()):
            start = answer.answer_text.find(part, offset)
            end = start + len(part)
            offset = end
            if (
                (direct.search(part) or subject.search(part))
                and not _NEGATION.search(part)
                and any(start <= span["start"] < end for span in mentions)
            ):
                recommendations.append({"start": start, "end": end, "text": part})
    domain = normalize_benchmark_domain(brand.domain)
    owned, backed = False, False
    for citation in answer.citations:
        if citation.evidence_type != "citation":
            continue
        valid_support = [
            span
            for span in citation.supports
            if 0 <= span.start < span.end <= len(answer.answer_text)
            and answer.answer_text[span.start : span.end] == span.text
        ]
        if not valid_support:
            continue
        host = normalize_benchmark_domain(citation.url)
        if domain and (host == domain or host.endswith("." + domain)):
            owned = True
        if answer.provenance.search_used is True:
            for support in valid_support:
                if any(support.start <= span["start"] and span["end"] <= support.end for span in mentions):
                    backed = True
    return BrandObservation(
        brand=brand.name,
        mentioned=bool(mentions),
        recommended=bool(recommendations),
        owned_domain_cited=owned,
        search_backed=backed,
        mention_spans=mentions,
        recommendation_spans=recommendations,
    )


def _prompt_rate(rows: list[tuple[CollectedAnswer, BrandObservation]], metric: str) -> float | None:
    values: dict[str, list[bool]] = defaultdict(list)
    for answer, observation in rows:
        if metric == "search_used":
            if answer.provenance.search_used is None:
                continue
            value = answer.provenance.search_used
        else:
            value = getattr(observation, metric)
        values[answer.prompt_id].append(value)
    return 100 * mean(mean(v) for v in values.values()) if values else None


def _condition_metrics(condition: str, rows: list[tuple[CollectedAnswer, BrandObservation]]) -> ConditionMetrics:
    attempts = [r for r in rows if r[0].provenance.condition == condition]
    valid = [r for r in attempts if r[0].status == "success" and r[0].answer_text.strip()]
    search_used = [r for r in valid if r[0].provenance.search_used is True]
    return ConditionMetrics(
        condition=condition,
        attempts=len(attempts),
        valid_answers=len(valid),
        prompt_count=len({a.prompt_id for a, _ in valid}),
        mentioned_answers=sum(o.mentioned for _, o in valid),
        recommended_answers=sum(o.recommended for _, o in valid),
        owned_domain_cited_answers=sum(o.owned_domain_cited for _, o in valid),
        search_used_answers=len(search_used),
        search_backed_answers=sum(o.search_backed for _, o in valid),
        statuses=dict(Counter(a.status for a, _ in attempts)),
        mention_rate=_prompt_rate(valid, "mentioned"),
        recommendation_rate=_prompt_rate(valid, "recommended"),
        owned_domain_citation_rate=_prompt_rate(valid, "owned_domain_cited"),
        search_use_rate=_prompt_rate(valid, "search_used"),
        search_observed_answers=sum(a.provenance.search_used is not None for a, _ in valid),
        search_unknown_answers=sum(a.provenance.search_used is None for a, _ in valid),
        search_backed_rate=_prompt_rate(valid, "search_backed"),
        search_used_mention_rate=_prompt_rate(search_used, "mentioned"),
    )


def _paired_differences(rows: list[tuple[CollectedAnswer, BrandObservation]]) -> tuple[list[PairedDifference], int]:
    pairs: dict[tuple[str, int], dict[str, BrandObservation]] = defaultdict(dict)
    valid = [r for r in rows if r[0].status == "success" and r[0].answer_text.strip()]
    for answer, observation in valid:
        pairs[(answer.prompt_id, answer.provenance.repetition)][answer.provenance.condition] = observation
    complete = {key: pair for key, pair in pairs.items() if set(pair) == set(_CONDITIONS)}
    differences = []
    for metric in ("mentioned", "recommended", "owned_domain_cited", "search_backed"):
        by_prompt: dict[str, list[float]] = defaultdict(list)
        for (prompt_id, _), pair in complete.items():
            by_prompt[prompt_id].append(
                float(getattr(pair["search_enabled"], metric)) - float(getattr(pair["unassisted"], metric))
            )
        values = [mean(v) for v in by_prompt.values()]
        low = high = None
        if len(values) >= 2:
            rng = random.Random(0)
            samples = sorted(
                100 * mean(rng.choices(values, k=len(values))) for _ in range(EXPERIMENT_BOOTSTRAP_SAMPLES)
            )
            low, high = samples[int(len(samples) * 0.025)], samples[int(len(samples) * 0.975)]
        differences.append(
            PairedDifference(
                metric=metric,
                pair_count=len(complete),
                prompt_count=len(by_prompt),
                delta_pp=100 * mean(values) if values else None,
                interval_low_pp=low,
                interval_high_pp=high,
            )
        )
    return differences, len(valid) - 2 * len(complete)


def build_memory_search_report(batch: CollectedAnswerBatch) -> MemorySearchReport:
    """Aggregate only explicit, matching controls; keep legacy provenance unknown."""
    manifest = validate_experiment(batch) if batch.experiment else None
    report = MemorySearchReport(
        experiment_id=manifest.experiment_id if manifest else "",
        collection_run_id=batch.collection_run_id,
        artifact_base=batch.artifact_base,
        prompt_set_hash=manifest.prompt_set_hash if manifest else "",
        configuration_hash=manifest.configuration_hash if manifest else "",
        generated_at=_now_iso(),
        total_attempts=len(batch.answers),
        generation_requests_made=sum(a.provenance.request_sent is True for a in batch.answers),
        status_counts=dict(Counter(a.status for a in batch.answers)),
        error_counts=dict(Counter(a.error_code for a in batch.answers if a.error_code)),
        observed_tokens=sum(a.provenance.usage.get("totalTokenCount", 0) for a in batch.answers),
        usage_unknown_attempts=sum("totalTokenCount" not in a.provenance.usage for a in batch.answers),
        observed_search_queries=sum(len(a.provenance.search_queries) for a in batch.answers),
        expected_attempts=len(batch.prompts) * manifest.repetitions * 2 if manifest else 0,
        notes=[
            "Memory share is unassisted recall, a proxy; training sources cannot be identified.",
            "Rates are percentages of eligible answers, averaged equally over prompts; brand shares need not sum to 100.",
            "Recommendations use conservative English/French explicit-verb rules; inspect evidence for interpretation.",
            "Search-enabled is not proof of search use. Missing search metadata remains unknown.",
            "Locale fields record requests; this API collector does not enforce country or certify effective language/region.",
            "Search-backed rates count observed citation-supported brand references, not attribution of every statement.",
            "Paired differences use complete pairs within one model version and surface; unmatched answers are separate.",
            "Intervals resample prompt clusters (95% percentile bootstrap); small pilots are exploratory.",
            "Citation domains use provider URLs without fetching redirects; unresolved URLs can undercount owned citations.",
        ],
    )
    report.missing_attempts = max(0, report.expected_attempts - report.total_attempts)
    prompts = {p.prompt_id: p for p in batch.prompts}
    cohorts: dict[tuple, list[CollectedAnswer]] = defaultdict(list)
    seen: set[tuple] = set()
    for answer in batch.answers:
        p = answer.provenance
        prompt = prompts.get(answer.prompt_id)
        eligible = bool(
            manifest
            and prompt
            and p.experiment_id == manifest.experiment_id
            and p.configuration_hash == manifest.configuration_hash
            and p.prompt_hash == content_hash(asdict(prompt))
            and answer.query_text == prompt.query_text
            and answer.provider == manifest.provider
            and answer.surface == manifest.surface
            and answer.collection_mode == "api"
            and answer.model == manifest.model
            and p.requested_model == manifest.model
            and p.context_isolated is True
            and p.condition in _CONDITIONS
            and 1 <= p.repetition <= manifest.repetitions
            and p.search_enabled is (p.condition == "search_enabled")
            and p.available_tools == (["googleSearch"] if p.condition == "search_enabled" else [])
            and (p.condition != "unassisted" or p.search_used is False)
            and (answer.status != "success" or bool(p.returned_model))
        )
        if eligible:
            identity = (answer.prompt_id, p.repetition, p.condition)
            if identity in seen:
                raise ValueError("Duplicate prompt/repetition/condition; each experiment slot must have one attempt")
            seen.add(identity)
            key = (
                answer.provider,
                answer.surface,
                p.requested_model,
                p.returned_model,
                answer.collection_mode,
                p.configuration_hash,
            )
            cohorts[key].append(answer)
        else:
            report.unclassified_attempts += 1
        report.evidence.append(
            {
                "prompt_id": answer.prompt_id,
                "query_text": answer.query_text,
                "condition": p.condition,
                "repetition": p.repetition,
                "status": answer.status,
                "error_code": answer.error_code,
                "classified": eligible,
                "answer_text": answer.answer_text,
                "raw_response_path": answer.raw_response_path,
                "provenance": asdict(p),
                "citations": [asdict(c) for c in answer.citations],
                "outcomes": [asdict(observe_brand(answer, b)) for b in [manifest.target, *manifest.competitors]]
                if manifest and answer.status == "success"
                else [],
            }
        )
    if manifest:
        for key, answers in sorted(cohorts.items()):
            for brand in [manifest.target, *manifest.competitors]:
                rows = [(a, observe_brand(a, brand)) for a in answers]
                differences, unmatched = _paired_differences(rows)
                report.slices.append(
                    ExperimentSlice(
                        provider=key[0],
                        surface=key[1],
                        requested_model=key[2],
                        returned_model=key[3],
                        collection_mode=key[4],
                        configuration_hash=key[5],
                        brand=brand.name,
                        conditions=[_condition_metrics(c, rows) for c in _CONDITIONS],
                        paired_differences=differences,
                        unmatched_valid_answers=unmatched,
                    )
                )
    return report


def compare_memory_search_waves(before: CollectedAnswerBatch, after: CollectedAnswerBatch) -> dict:
    """Compare identical observation slots, retaining model and coverage boundaries."""
    first, second = validate_experiment(before), validate_experiment(after)
    if first.configuration_hash != second.configuration_hash or first.prompt_set_hash != second.prompt_set_hash:
        raise ValueError("Noncomparable waves: prompts, model, surface, or generation settings changed")
    if first.repetitions != second.repetitions:
        raise ValueError("Noncomparable waves: repetition count changed")
    if [asdict(first.target), *map(asdict, first.competitors)] != [
        asdict(second.target),
        *map(asdict, second.competitors),
    ]:
        raise ValueError("Noncomparable waves: tracked brands changed")
    reports = [build_memory_search_report(batch) for batch in (before, after)]
    indices = []
    for batch, report in zip((before, after), reports):
        index = {}
        for answer, evidence in zip(batch.answers, report.evidence):
            if evidence["classified"] and answer.status == "success" and answer.answer_text.strip():
                p = answer.provenance
                index[(answer.prompt_id, p.repetition, p.condition, p.returned_model)] = answer
        indices.append(index)
    shared = set(indices[0]) & set(indices[1])
    changes = []
    for brand in [first.target, *first.competitors]:
        for condition, version in sorted({(key[2], key[3]) for key in shared}):
            keys = sorted(key for key in shared if key[2:] == (condition, version))
            rows = [[(index[key], observe_brand(index[key], brand)) for key in keys] for index in indices]
            deltas: dict[str, float | None] = {}
            counts = {}
            for metric in ("mentioned", "recommended", "owned_domain_cited", "search_backed"):
                old_rate, new_rate = (_prompt_rate(wave, metric) for wave in rows)
                deltas[metric + "_delta_pp"] = None if old_rate is None or new_rate is None else new_rate - old_rate
                counts[metric] = {
                    "before": sum(getattr(o, metric) for _, o in rows[0]),
                    "after": sum(getattr(o, metric) for _, o in rows[1]),
                }
            changes.append(
                {
                    "brand": brand.name,
                    "returned_model": version,
                    "condition": condition,
                    "matched_answers_per_wave": len(keys),
                    "matched_prompts": len({key[0] for key in keys}),
                    "counts": counts,
                    "mention_delta_pp": deltas["mentioned_delta_pp"],
                    **deltas,
                }
            )
    return {
        "before_experiment_id": first.experiment_id,
        "after_experiment_id": second.experiment_id,
        "before_collection_run_id": before.collection_run_id,
        "after_collection_run_id": after.collection_run_id,
        "comparable_model_versions": bool(shared),
        "matched_observation_slots": len(shared),
        "unmatched_before": len(indices[0]) - len(shared),
        "unmatched_after": len(indices[1]) - len(shared),
        "changes": changes,
        "note": "Observed before/after association on identical valid prompt/trial/condition/model-version slots; not causal proof.",
    }

"""Normalize raw provider payloads and canonical batches for benchmark runs."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from geo_optimizer.core.collection.store import COLLECTION_HOME, PARSER_VERSION
from geo_optimizer.core.snapshots import extract_citations
from geo_optimizer.models.results.collection import (
    COLLECTION_SCHEMA_VERSION,
    CollectedAnswer,
    CollectedAnswerBatch,
    CollectedCitation,
    PromptSpec,
)


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _citations_from_urls(urls: list[str], *, titles: dict[str, str] | None = None) -> list[CollectedCitation]:
    citations: list[CollectedCitation] = []
    seen: set[str] = set()
    titles = titles or {}
    for index, url in enumerate(urls, start=1):
        cleaned = url.rstrip(").,;]")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        citations.append(
            CollectedCitation(
                url=cleaned,
                domain=_domain_from_url(cleaned),
                title=titles.get(cleaned, ""),
                position=index,
            )
        )
    return citations


def answer_to_benchmark_row(answer: CollectedAnswer) -> dict:
    """Map canonical answer to legacy benchmark runner dict."""
    citation_urls = [item.url for item in answer.citations if item.url]
    if not citation_urls:
        citation_urls = [item.url for item in extract_citations(answer.answer_text)]
    return {
        "prompt": answer.query_text,
        "answer_text": answer.answer_text,
        "provider": answer.provider,
        "model": answer.model,
        "task": answer.query_class,
        "keyword_topic": answer.keyword_topic,
        "persona": answer.persona,
        "citation_urls": citation_urls,
        "prompt_id": answer.prompt_id,
        "collection_mode": answer.collection_mode,
        "parse_confidence": answer.parse_confidence,
    }


def batch_to_benchmark_answers(batch: CollectedAnswerBatch) -> list[dict]:
    """Convert a canonical batch into benchmark runner input rows."""
    return [
        answer_to_benchmark_row(answer)
        for answer in batch.answers
        if answer.query_text
        and answer.answer_text
        and answer.status == "success"
        and not answer.answer_text.startswith("[collection error:")
    ]


def batch_to_dict(batch: CollectedAnswerBatch) -> dict:
    """Serialize batch for JSON export."""

    def _answer_dict(answer: CollectedAnswer) -> dict:
        return {
            "prompt_id": answer.prompt_id,
            "query_text": answer.query_text,
            "query_class": answer.query_class,
            "provider": answer.provider,
            "surface": answer.surface,
            "model": answer.model,
            "country": answer.country,
            "language": answer.language,
            "device": answer.device,
            "logged_in_state": answer.logged_in_state,
            "answer_text": answer.answer_text if answer.status == "success" else "",
            "citations": [
                {
                    "url": c.url,
                    "domain": c.domain,
                    "title": c.title,
                    "position": c.position,
                    "snippet": c.snippet,
                }
                for c in answer.citations
            ],
            "mentioned_domains": answer.mentioned_domains,
            "mentioned_brands": answer.mentioned_brands,
            "raw_response_path": answer.raw_response_path,
            "rendered_html_path": answer.rendered_html_path,
            "screenshot_path": answer.screenshot_path,
            "collection_mode": answer.collection_mode,
            "parser_version": answer.parser_version,
            "parse_confidence": answer.parse_confidence,
            "collected_at": answer.collected_at,
            "keyword_topic": answer.keyword_topic,
            "persona": answer.persona,
            "status": answer.status,
            "error_code": answer.error_code,
        }

    return {
        "schema_version": batch.schema_version,
        "target_domain": batch.target_domain,
        "collection_run_id": batch.collection_run_id,
        "prompts": [
            {
                "prompt_id": prompt.prompt_id,
                "query_text": prompt.query_text,
                "query_class": prompt.query_class,
                "keyword_topic": prompt.keyword_topic,
                "persona": prompt.persona,
                "country": prompt.country,
                "language": prompt.language,
            }
            for prompt in batch.prompts
        ],
        "answers": [_answer_dict(answer) for answer in batch.answers],
    }


def batch_from_dict(payload: dict) -> CollectedAnswerBatch:
    """Load canonical batch from JSON dict."""
    version = str(payload.get("schema_version", ""))
    if version and version != COLLECTION_SCHEMA_VERSION:
        # Forward-compatible: accept unknown minor versions
        pass

    prompts = [
        PromptSpec(
            prompt_id=str(item.get("prompt_id", "")),
            query_text=str(item.get("query_text", item.get("prompt", ""))),
            query_class=str(item.get("query_class", item.get("task", ""))),
            keyword_topic=str(item.get("keyword_topic", "")),
            persona=str(item.get("persona", "")),
            country=str(item.get("country", "")),
            language=str(item.get("language", "en")),
        )
        for item in payload.get("prompts", [])
    ]

    answers: list[CollectedAnswer] = []
    for item in payload.get("answers", []):
        answer_text = str(item.get("answer_text", ""))
        legacy_error = answer_text.startswith("[collection error:")
        raw_status = str(item.get("status", "success")).strip().lower()
        status = "success" if not legacy_error and raw_status in {"success", "ok", "done", "completed"} else "error"
        citations = [
            CollectedCitation(
                url=str(c.get("url", "")),
                domain=str(c.get("domain", "")),
                title=str(c.get("title", "")),
                position=int(c.get("position", 0)),
                snippet=str(c.get("snippet", "")),
            )
            for c in item.get("citations", [])
        ]
        answers.append(
            CollectedAnswer(
                prompt_id=str(item.get("prompt_id", "")),
                query_text=str(item.get("query_text", item.get("prompt", ""))),
                query_class=str(item.get("query_class", item.get("task", ""))),
                provider=str(item.get("provider", "")),
                surface=str(item.get("surface", item.get("provider", ""))),
                model=str(item.get("model", "")),
                country=str(item.get("country", "")),
                language=str(item.get("language", "en")),
                device=str(item.get("device", "desktop")),
                logged_in_state=str(item.get("logged_in_state", "unknown")),
                answer_text=answer_text if status == "success" else "",
                citations=citations,
                mentioned_domains=list(item.get("mentioned_domains", [])),
                mentioned_brands=list(item.get("mentioned_brands", [])),
                raw_response_path=str(item.get("raw_response_path", "")),
                rendered_html_path=str(item.get("rendered_html_path", "")),
                screenshot_path=str(item.get("screenshot_path", "")),
                collection_mode=str(item.get("collection_mode", "api")),
                parser_version=str(item.get("parser_version", PARSER_VERSION)),
                parse_confidence=float(item.get("parse_confidence", 1.0)),
                collected_at=str(item.get("collected_at", "")),
                keyword_topic=str(item.get("keyword_topic", "")),
                persona=str(item.get("persona", "")),
                status=status,
                error_code="collection_failed" if legacy_error else str(item.get("error_code", "")),
            )
        )

    # Legacy v0: top-level "answers" with prompt/answer_text only
    if not answers and "answers" not in payload and isinstance(payload.get("entries"), list):
        pass

    legacy_answers = payload.get("answers")
    if not answers and isinstance(legacy_answers, list):
        for item in legacy_answers:
            if "query_text" in item or "query_class" in item:
                continue
            query = str(item.get("prompt", ""))
            text = str(item.get("answer_text", ""))
            urls = list(item.get("citation_urls", []))
            answers.append(
                CollectedAnswer(
                    query_text=query,
                    query_class=str(item.get("task", "")),
                    provider=str(item.get("provider", "")),
                    surface=str(item.get("provider", "")),
                    model=str(item.get("model", "")),
                    answer_text=text,
                    citations=_citations_from_urls(urls),
                    keyword_topic=str(item.get("keyword_topic", "")),
                    persona=str(item.get("persona", "")),
                    collection_mode=str(item.get("collection_mode", "manual")),
                    parser_version=PARSER_VERSION,
                )
            )

    return CollectedAnswerBatch(
        schema_version=str(payload.get("schema_version", COLLECTION_SCHEMA_VERSION)),
        target_domain=str(payload.get("target_domain", "")),
        collection_run_id=str(payload.get("collection_run_id", "")),
        prompts=prompts,
        answers=answers,
    )


def load_canonical_batch(path: Path) -> CollectedAnswerBatch:
    """Load canonical or legacy answers JSON from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"schema_version": COLLECTION_SCHEMA_VERSION, "answers": payload}
    return batch_from_dict(payload)


def write_canonical_batch(path: Path, batch: CollectedAnswerBatch) -> None:
    """Write canonical answers.json contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(batch_to_dict(batch), indent=2), encoding="utf-8")


def export_benchmark_answers_file(
    canonical_path: Path,
    output_path: Path,
    *,
    include_metadata: bool = False,
) -> list[dict]:
    """Read canonical file and write benchmark-compatible JSON."""
    batch = load_canonical_batch(canonical_path)
    rows = batch_to_benchmark_answers(batch)
    payload: dict = {"answers": rows}
    if include_metadata:
        payload["schema_version"] = batch.schema_version
        payload["target_domain"] = batch.target_domain
        payload["collection_run_id"] = batch.collection_run_id
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return rows


def resolve_artifact_path(relative: str) -> Path:
    """Resolve artifact path relative to collection home."""
    if not relative:
        return Path()
    path = Path(relative)
    if path.is_absolute():
        return path
    return COLLECTION_HOME / path

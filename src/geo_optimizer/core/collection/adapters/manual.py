"""Manual lane — load pre-reviewed answers from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from geo_optimizer.core.collection.normalize import batch_from_dict
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import PARSER_VERSION, _now_iso
from geo_optimizer.models.results.collection import CollectedAnswer


class ManualFileAdapter:
    """Serve answers from a hand-checked JSON file (quality control layer)."""

    provider_id = "manual"
    collection_mode = "manual"
    surface = "manual_review"

    def __init__(self, *, source_path: Path):
        self.source_path = source_path
        self._index: dict[str, CollectedAnswer] = {}
        self._load()

    def _load(self) -> None:
        payload = json.loads(self.source_path.read_text(encoding="utf-8"))
        batch = batch_from_dict(payload if isinstance(payload, dict) else {"answers": payload})
        for answer in batch.answers:
            key = answer.prompt_id or answer.query_text
            self._index[key] = answer

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        key = request.prompt.prompt_id or request.prompt.query_text
        if key not in self._index:
            raise KeyError(f"No manual answer for prompt_id={request.prompt.prompt_id!r}")
        answer = self._index[key]
        return CollectedAnswer(
            prompt_id=request.prompt.prompt_id,
            query_text=request.prompt.query_text,
            query_class=request.prompt.query_class or answer.query_class,
            provider=answer.provider or self.provider_id,
            surface=self.surface,
            model=answer.model,
            answer_text=answer.answer_text,
            citations=list(answer.citations),
            mentioned_domains=list(answer.mentioned_domains),
            mentioned_brands=list(answer.mentioned_brands),
            collection_mode=self.collection_mode,
            parser_version=PARSER_VERSION,
            parse_confidence=1.0,
            collected_at=answer.collected_at or _now_iso(),
            keyword_topic=request.prompt.keyword_topic or answer.keyword_topic,
            persona=request.prompt.persona or answer.persona,
        )

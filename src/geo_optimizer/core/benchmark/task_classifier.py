"""Rule-based task classification with optional LLM hook."""

from __future__ import annotations

import json
import re

from geo_optimizer.models.config import TASK_CLASSIFIER_SIGNALS, TASK_TAXONOMY
from geo_optimizer.models.results.benchmark import TaskClassification

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def classify_text(
    text: str,
    *,
    hint_task: str = "",
    use_llm: bool = False,
    llm_classifier=None,
) -> TaskClassification:
    """Classify free text into a task taxonomy label.

    Args:
        text: Prompt, keyword, page excerpt, or answer text.
        hint_task: Optional pre-assigned task (validated against taxonomy).
        use_llm: When True, call ``llm_classifier(text)`` if provided.
        llm_classifier: Callable returning dict with task, confidence, signals.
    """
    if hint_task and hint_task in TASK_TAXONOMY:
        return TaskClassification(task=hint_task, confidence=1.0, signals=["hint"], source="hint")

    if use_llm and llm_classifier is not None:
        raw = llm_classifier(text)
        if isinstance(raw, str):
            raw = json.loads(raw)
        task = str(raw.get("task", ""))
        if task in TASK_TAXONOMY:
            return TaskClassification(
                task=task,
                confidence=float(raw.get("confidence", 0.7)),
                signals=list(raw.get("signals", [])),
                source="llm",
            )

    normalized = f" {_normalize_text(text)} "
    scores: dict[str, tuple[int, list[str]]] = {}
    for task, signals in TASK_CLASSIFIER_SIGNALS.items():
        hits = [sig for sig in signals if sig in normalized or sig in text.lower()]
        if hits:
            scores[task] = (len(hits), hits)

    if not scores:
        return TaskClassification(task="discovery", confidence=0.35, signals=["default"], source="rules")

    best_task = max(scores, key=lambda key: scores[key][0])
    hit_count, matched = scores[best_task]
    max_possible = max(len(signals) for signals in TASK_CLASSIFIER_SIGNALS.values()) or 1
    confidence = min(0.98, 0.45 + (hit_count / max_possible) * 0.5)
    return TaskClassification(task=best_task, confidence=round(confidence, 2), signals=matched, source="rules")


def classify_prompt(prompt: str, **kwargs) -> TaskClassification:
    """Classify a tracked prompt."""
    return classify_text(prompt, **kwargs)


def classify_keyword(keyword: str, **kwargs) -> TaskClassification:
    """Classify a keyword/topic string."""
    return classify_text(keyword, **kwargs)


def classify_page(page_text: str, **kwargs) -> TaskClassification:
    """Classify page content (title + headings + lead)."""
    return classify_text(page_text, **kwargs)


def classify_answer(answer_text: str, prompt: str = "", **kwargs) -> TaskClassification:
    """Classify an AI answer; falls back to prompt context when weak."""
    answer_cls = classify_text(answer_text, **kwargs)
    if answer_cls.confidence >= 0.6:
        return answer_cls
    if prompt:
        prompt_cls = classify_text(prompt, **kwargs)
        if prompt_cls.confidence > answer_cls.confidence:
            return TaskClassification(
                task=prompt_cls.task,
                confidence=round((prompt_cls.confidence + answer_cls.confidence) / 2, 2),
                signals=prompt_cls.signals + answer_cls.signals,
                source="rules",
            )
    return answer_cls

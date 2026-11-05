from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


_POSITIVE_WORDS = frozenset([
    "best", "top", "great", "excellent", "recommend", "leading", "popular",
    "powerful", "trusted", "reliable", "effective", "outstanding", "superior",
    "favourite", "favorite", "preferred", "love", "amazing", "impressive",
])

_NEGATIVE_WORDS = frozenset([
    "worst", "avoid", "poor", "bad", "terrible", "expensive", "overpriced",
    "buggy", "slow", "disappointing", "unreliable", "difficult", "complex",
    "limited", "lacking", "inferior", "weak", "outdated",
])

_URL_RE = re.compile(r"https?://[^\s\)\]\>\"']+")
_NUMBERED_LIST_RE = re.compile(r"(?:^|\n)\s*(\d+)[.)]\s+(.+)", re.MULTILINE)


@dataclass
class BrandIntelligence:
    mentioned: bool
    mention_count: int
    rank: Optional[int]
    sentiment: str  # "positive" | "negative" | "neutral"
    citations: List[str] = field(default_factory=list)


def _all_terms(brand: str, aliases: List[str]) -> List[str]:
    return [brand] + aliases


def _find_mentions(text: str, terms: List[str]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    lower = text.lower()
    for term in terms:
        t = term.lower()
        start = 0
        while True:
            idx = lower.find(t, start)
            if idx == -1:
                break
            hits.append((idx, term))
            start = idx + 1
    hits.sort(key=lambda x: x[0])
    return hits


def _extract_rank(text: str, terms: List[str]) -> Optional[int]:
    lower_terms = [t.lower() for t in terms]
    for match in _NUMBERED_LIST_RE.finditer(text):
        number = int(match.group(1))
        item_text = match.group(2).lower()
        if any(term in item_text for term in lower_terms):
            return number
    return None


def _score_sentiment(text: str, hits: List[Tuple[int, str]]) -> str:
    pos = neg = 0
    lower = text.lower()
    for offset, _ in hits:
        window = lower[max(0, offset - 150): offset + 150]
        words = set(re.findall(r"\w+", window))
        pos += len(words & _POSITIVE_WORDS)
        neg += len(words & _NEGATIVE_WORDS)
    if pos == 0 and neg == 0:
        return "neutral"
    return "positive" if pos >= neg else "negative"


def _extract_citations(text: str) -> List[str]:
    return list(dict.fromkeys(_URL_RE.findall(text)))


def analyze(text: str, brand: str, aliases: List[str]) -> BrandIntelligence:
    terms = _all_terms(brand, aliases)
    hits = _find_mentions(text, terms)
    return BrandIntelligence(
        mentioned=len(hits) > 0,
        mention_count=len(hits),
        rank=_extract_rank(text, terms) if hits else None,
        sentiment=_score_sentiment(text, hits) if hits else "neutral",
        citations=_extract_citations(text),
    )

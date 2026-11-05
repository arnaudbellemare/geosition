"""
GEO Audit — Embedding Proximity Score (#354).

Simulates RAG retrieval by computing cosine similarity between page chunks
and representative queries using sentence-transformers.

Requires: pip install geosition[embedding]
Gracefully skips when sentence-transformers is not installed.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from geo_optimizer.models.results import EmbeddingProximityResult, QueryScore

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_RETRIEVAL_THRESHOLD = 0.45

# Representative queries that a RAG system might use to retrieve content
_SAMPLE_QUERIES = [
    "What does this company do?",
    "What services or products are offered?",
    "Who is the author or organization behind this content?",
    "What are the key facts and statistics mentioned?",
    "How does this compare to alternatives?",
]


def _configure_embedding_cache_dirs() -> None:
    """Point embedding caches to a writable local GEO directory."""
    from geo_optimizer.models.config import GEO_OPTIMIZER_HOME

    cache_root = GEO_OPTIMIZER_HOME / "hf-cache"
    try:
        Path(cache_root).mkdir(parents=True, exist_ok=True)
    except OSError:
        # In restricted environments (sandbox/CI), the home path may be
        # read-only. Fall back to system temp to avoid noisy cache errors.
        cache_root = Path(tempfile.gettempdir()) / "geo-optimizer-hf-cache"
        Path(cache_root).mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(cache_root))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_root / "hub"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache_root / "sentence-transformers"))


def audit_embedding_proximity(
    soup,
    soup_clean=None,
    model_name: str = _DEFAULT_MODEL,
    queries: list[str] | None = None,
) -> EmbeddingProximityResult:
    """Compute embedding similarity between page chunks and sample queries.

    Args:
        soup: BeautifulSoup of the full HTML document.
        soup_clean: Optional pre-cleaned soup (scripts/styles removed).
        model_name: Sentence-transformer model name.
        queries: Custom queries (defaults to _SAMPLE_QUERIES).

    Returns:
        EmbeddingProximityResult with similarity scores.
    """
    _configure_embedding_cache_dirs()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return EmbeddingProximityResult(
            checked=True,
            skipped_reason="sentence-transformers not installed (pip install geosition[embedding])",
        )

    body = (soup_clean or soup).find("body") if soup else None
    if not body:
        return EmbeddingProximityResult(checked=True, skipped_reason="No body content")

    chunks = _extract_chunks(body)
    if not chunks:
        return EmbeddingProximityResult(checked=True, skipped_reason="No text chunks found")

    queries = queries or _SAMPLE_QUERIES

    try:
        model = SentenceTransformer(model_name)
        chunk_embeddings = model.encode(chunks, show_progress_bar=False)
        query_embeddings = model.encode(queries, show_progress_bar=False)
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        logger.warning("Embedding model unavailable: %s", type(exc).__name__)
        return EmbeddingProximityResult(
            checked=True,
            skipped_reason=f"embedding not installed or unavailable ({type(exc).__name__})",
        )

    from sentence_transformers import util as st_util

    query_scores = []
    all_max_scores: list[float] = []

    for i, query in enumerate(queries):
        similarities = st_util.cos_sim(query_embeddings[i], chunk_embeddings)[0]
        max_sim = float(similarities.max())
        all_max_scores.append(max_sim)
        query_scores.append(QueryScore(query=query, max_similarity=round(max_sim, 4)))

    retrievable = sum(
        1
        for c in range(len(chunks))
        if any(
            float(st_util.cos_sim(query_embeddings[q], chunk_embeddings[c])[0][0]) >= _RETRIEVAL_THRESHOLD
            for q in range(len(queries))
        )
    )

    avg_sim = sum(all_max_scores) / len(all_max_scores) if all_max_scores else 0.0
    top_sim = max(all_max_scores) if all_max_scores else 0.0

    return EmbeddingProximityResult(
        checked=True,
        model_name=model_name,
        query_scores=query_scores,
        avg_similarity=round(avg_sim, 4),
        top_similarity=round(top_sim, 4),
        retrievable_chunks=retrievable,
        total_chunks=len(chunks),
    )


def _extract_chunks(body) -> list[str]:
    """Extract text chunks from body, split by headings or paragraphs."""
    headings = body.find_all(re.compile(r"^h[1-6]$"))

    if headings:
        headings_set = set(headings)
        chunks: list[str] = []
        for heading in headings:
            parts: list[str] = []
            for sibling in heading.next_siblings:
                if sibling in headings_set:
                    break
                t = (
                    sibling.get_text(separator=" ", strip=True)
                    if hasattr(sibling, "get_text")
                    else str(sibling).strip()
                )
                if t:
                    parts.append(t)
            text = " ".join(parts).strip()
            if len(text.split()) >= 10:
                chunks.append(text)
        return chunks

    # Fallback: split by paragraphs
    paragraphs = body.find_all("p")
    return [p.get_text(separator=" ", strip=True) for p in paragraphs if len(p.get_text(strip=True).split()) >= 10]

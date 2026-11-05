"""Hybrid answer collection: API, browser, and manual lanes."""

from __future__ import annotations

from geo_optimizer.core.collection.normalize import load_canonical_batch
from geo_optimizer.core.collection.pipeline import (
    collect_and_normalize,
    export_benchmark_answers_file,
    normalize_raw_directory,
)
from geo_optimizer.core.collection.protocol import AnswerCollectorAdapter, CollectionRequest

__all__ = [
    "AnswerCollectorAdapter",
    "CollectionRequest",
    "collect_and_normalize",
    "export_benchmark_answers_file",
    "load_canonical_batch",
    "normalize_raw_directory",
]

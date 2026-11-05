"""Domain GEO benchmark: tasks, citations, competitors, and aggregate scoring."""

from __future__ import annotations

from geo_optimizer.core.benchmark.runner import run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore

__all__ = ["BenchmarkStore", "run_domain_benchmark"]

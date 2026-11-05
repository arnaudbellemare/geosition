"""Benchmark run scheduling helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.models.config import BENCHMARK_SCHEDULES
from geo_optimizer.models.results.benchmark import BenchmarkScheduleRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


def compute_next_run(frequency: str, *, from_time: datetime | None = None) -> str | None:
    """Return ISO timestamp for next scheduled run."""
    if frequency == "manual":
        return None
    base = from_time or _now()
    delta = timedelta(days=1) if frequency == "daily" else timedelta(days=7)
    return (base + delta).isoformat()


def mark_schedule_run(
    domain: str,
    *,
    store: BenchmarkStore | None = None,
    frequency: str | None = None,
) -> BenchmarkScheduleRecord | None:
    """Update last_run_at and next_run_at after a benchmark completes."""
    benchmark_store = store or BenchmarkStore()
    schedule = benchmark_store.get_schedule(domain)
    if schedule is None:
        return None
    freq = frequency or schedule.frequency
    if freq not in BENCHMARK_SCHEDULES:
        freq = "weekly"
    now_iso = _now().isoformat()
    next_iso = compute_next_run(freq)
    return benchmark_store.update_schedule_run_times(domain, last_run_at=now_iso, next_run_at=next_iso)


def due_schedules(*, store: BenchmarkStore | None = None) -> list[BenchmarkScheduleRecord]:
    """Return enabled schedules that are due to run."""
    benchmark_store = store or BenchmarkStore()
    now_iso = _now().isoformat()
    due: list[BenchmarkScheduleRecord] = []
    with benchmark_store._connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM benchmark_schedules
            WHERE enabled = 1 AND frequency != 'manual'
            AND (next_run_at IS NULL OR next_run_at <= ?)
            """,
            (now_iso,),
        ).fetchall()
    for row in rows:
        due.append(
            BenchmarkScheduleRecord(
                schedule_id=int(row["id"]),
                domain=row["domain"],
                frequency=row["frequency"],
                competitor_domains=json.loads(row["competitor_domains_json"]),
                last_run_at=row["last_run_at"],
                next_run_at=row["next_run_at"],
                enabled=bool(row["enabled"]),
            )
        )
    return due

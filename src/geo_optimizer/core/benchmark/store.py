"""SQLite persistence for domain GEO benchmark entities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.core.benchmark.monitoring import build_citation_share_summary
from geo_optimizer.models.config import DEFAULT_BENCHMARK_RETENTION_DAYS
from geo_optimizer.models.results.benchmark import (
    BenchmarkRunRecord,
    BenchmarkScheduleRecord,
    BenchmarkScoreBreakdown,
    CitationShareSummary,
    CitationSnapshotRecord,
    CompetitorMentionRecord,
    EvidenceArtifactRecord,
    PageTaskCoverageRecord,
    TrackedPromptRecord,
)
from geo_optimizer.storage.paths import resolve_benchmark_db_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BenchmarkStore:
    """Local SQLite store for benchmark runs, prompts, and citation snapshots."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or resolve_benchmark_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracked_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_text TEXT NOT NULL,
                    task TEXT NOT NULL DEFAULT '',
                    keyword_topic TEXT NOT NULL DEFAULT '',
                    persona TEXT NOT NULL DEFAULT '',
                    target_domain TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS citation_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    prompt_id INTEGER,
                    prompt_text TEXT NOT NULL,
                    task TEXT NOT NULL,
                    task_confidence REAL NOT NULL DEFAULT 0,
                    answer_text TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (prompt_id) REFERENCES tracked_prompts(id) ON DELETE SET NULL,
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS citation_snapshot_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    citation_url TEXT NOT NULL,
                    citation_domain TEXT NOT NULL,
                    citation_position INTEGER NOT NULL,
                    FOREIGN KEY (snapshot_id) REFERENCES citation_snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS competitor_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    competitor_domain TEXT NOT NULL,
                    competitor_name TEXT NOT NULL DEFAULT '',
                    cited INTEGER NOT NULL DEFAULT 0,
                    mentioned INTEGER NOT NULL DEFAULT 0,
                    position INTEGER NOT NULL DEFAULT 0,
                    sentiment TEXT NOT NULL DEFAULT 'neutral',
                    FOREIGN KEY (snapshot_id) REFERENCES citation_snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS page_task_coverage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    supported_tasks TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    missing_evidence TEXT NOT NULL,
                    schema_support INTEGER NOT NULL DEFAULT 0,
                    citation_readiness INTEGER NOT NULL DEFAULT 0,
                    serp_alignment INTEGER NOT NULL DEFAULT 0,
                    backlink_support INTEGER NOT NULL DEFAULT 0,
                    performance_blockers TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    schedule TEXT NOT NULL DEFAULT 'manual',
                    benchmark_score INTEGER NOT NULL,
                    band TEXT NOT NULL,
                    breakdown_json TEXT NOT NULL,
                    provider_coverage_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS benchmark_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL UNIQUE,
                    frequency TEXT NOT NULL,
                    competitor_domains_json TEXT NOT NULL DEFAULT '[]',
                    last_run_at TEXT,
                    next_run_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_tracked_prompts_domain
                    ON tracked_prompts (target_domain);
                CREATE INDEX IF NOT EXISTS idx_citation_snapshots_run
                    ON citation_snapshots (run_id, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_benchmark_runs_domain_time
                    ON benchmark_runs (domain, run_at DESC);
                """
            )

    def upsert_tracked_prompt(
        self,
        prompt_text: str,
        target_domain: str,
        *,
        task: str = "",
        keyword_topic: str = "",
        persona: str = "",
    ) -> TrackedPromptRecord:
        """Insert a tracked prompt for a domain."""
        domain = normalize_benchmark_domain(target_domain)
        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tracked_prompts (
                    prompt_text, task, keyword_topic, persona, target_domain, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (prompt_text, task, keyword_topic, persona, domain, created_at),
            )
            prompt_id = int(cursor.lastrowid or 0)
        return TrackedPromptRecord(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            task=task,
            keyword_topic=keyword_topic,
            persona=persona,
            target_domain=domain,
            created_at=created_at,
        )

    def list_tracked_prompts(self, target_domain: str) -> list[TrackedPromptRecord]:
        """List prompts registered for a domain."""
        domain = normalize_benchmark_domain(target_domain)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tracked_prompts WHERE target_domain = ? ORDER BY id ASC",
                (domain,),
            ).fetchall()
        return [
            TrackedPromptRecord(
                prompt_id=int(row["id"]),
                prompt_text=row["prompt_text"],
                task=row["task"],
                keyword_topic=row["keyword_topic"],
                persona=row["persona"],
                target_domain=row["target_domain"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_citation_snapshot(
        self,
        *,
        run_id: int,
        provider: str,
        model: str,
        prompt_text: str,
        task: str,
        task_confidence: float,
        answer_text: str,
        cited_urls: list[tuple[str, str, int]],
        prompt_id: int | None = None,
        recorded_at: str | None = None,
    ) -> CitationSnapshotRecord:
        """Persist one AI answer and its cited URLs."""
        timestamp = recorded_at or _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO citation_snapshots (
                    run_id, provider, model_name, prompt_id, prompt_text,
                    task, task_confidence, answer_text, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    provider,
                    model,
                    prompt_id,
                    prompt_text,
                    task,
                    task_confidence,
                    answer_text,
                    timestamp,
                ),
            )
            snapshot_id = int(cursor.lastrowid or 0)
            urls: list[str] = []
            positions: list[int] = []
            for url, domain, position in cited_urls:
                conn.execute(
                    """
                    INSERT INTO citation_snapshot_urls (
                        snapshot_id, citation_url, citation_domain, citation_position
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (snapshot_id, url, domain, position),
                )
                urls.append(url)
                positions.append(position)
        return CitationSnapshotRecord(
            snapshot_id=snapshot_id,
            provider=provider,
            model=model,
            prompt_id=prompt_id or 0,
            prompt_text=prompt_text,
            task=task,
            task_confidence=task_confidence,
            answer_text=answer_text,
            recorded_at=timestamp,
            cited_urls=urls,
            citation_positions=positions,
        )

    def save_competitor_mentions(
        self,
        snapshot_id: int,
        mentions: list[CompetitorMentionRecord],
    ) -> list[CompetitorMentionRecord]:
        """Persist competitor mentions for a snapshot."""
        saved: list[CompetitorMentionRecord] = []
        with self._connect() as conn:
            for mention in mentions:
                cursor = conn.execute(
                    """
                    INSERT INTO competitor_mentions (
                        snapshot_id, competitor_domain, competitor_name,
                        cited, mentioned, position, sentiment
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        mention.competitor_domain,
                        mention.competitor_name,
                        1 if mention.cited else 0,
                        1 if mention.mentioned else 0,
                        mention.position,
                        mention.sentiment,
                    ),
                )
                saved.append(
                    CompetitorMentionRecord(
                        mention_id=int(cursor.lastrowid or 0),
                        snapshot_id=snapshot_id,
                        competitor_domain=mention.competitor_domain,
                        competitor_name=mention.competitor_name,
                        cited=mention.cited,
                        mentioned=mention.mentioned,
                        position=mention.position,
                        sentiment=mention.sentiment,
                    )
                )
        return saved

    def save_page_task_coverage(
        self,
        run_id: int,
        records: list[PageTaskCoverageRecord],
    ) -> None:
        """Persist page-to-task coverage rows for a run."""
        with self._connect() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO page_task_coverage (
                        run_id, url, supported_tasks, confidence, missing_evidence,
                        schema_support, citation_readiness, serp_alignment,
                        backlink_support, performance_blockers
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        record.url,
                        json.dumps(record.supported_tasks),
                        record.confidence,
                        json.dumps(record.missing_evidence),
                        1 if record.schema_support else 0,
                        record.citation_readiness,
                        record.serp_alignment,
                        record.backlink_support,
                        json.dumps(record.performance_blockers),
                    ),
                )

    def save_benchmark_run(
        self,
        domain: str,
        *,
        schedule: str,
        benchmark_score: int,
        band: str,
        breakdown: BenchmarkScoreBreakdown,
        provider_coverage: dict[str, int],
        run_at: str | None = None,
    ) -> BenchmarkRunRecord:
        """Persist aggregate benchmark run."""
        normalized = normalize_benchmark_domain(domain)
        timestamp = run_at or _now_iso()
        breakdown_payload = {
            "citation_share": breakdown.citation_share,
            "task_coverage": breakdown.task_coverage,
            "competitor_position": breakdown.competitor_position,
            "unique_value": breakdown.unique_value,
            "domain_backlink": breakdown.domain_backlink,
            "serp_rank": breakdown.serp_rank,
            "technical_performance": breakdown.technical_performance,
            "scoring_version": breakdown.scoring_version,
            "measured_weight": breakdown.measured_weight,
        }
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO benchmark_runs (
                    domain, run_at, schedule, benchmark_score, band,
                    breakdown_json, provider_coverage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    timestamp,
                    schedule,
                    benchmark_score,
                    band,
                    json.dumps(breakdown_payload),
                    json.dumps(provider_coverage),
                ),
            )
            run_id = int(cursor.lastrowid or 0)
        return BenchmarkRunRecord(
            run_id=run_id,
            domain=normalized,
            run_at=timestamp,
            schedule=schedule,
            benchmark_score=benchmark_score,
            band=band,
            breakdown=breakdown,
            provider_coverage=provider_coverage,
        )

    def save_evidence_artifact(
        self,
        run_id: int,
        artifact_type: str,
        label: str,
        payload: str,
        *,
        recorded_at: str | None = None,
    ) -> EvidenceArtifactRecord:
        """Attach exportable proof to a benchmark run."""
        timestamp = recorded_at or _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO evidence_artifacts (run_id, artifact_type, label, payload, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, artifact_type, label, payload, timestamp),
            )
            artifact_id = int(cursor.lastrowid or 0)
        return EvidenceArtifactRecord(
            artifact_id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            label=label,
            payload=payload,
            recorded_at=timestamp,
        )

    def get_snapshots_for_run(self, run_id: int) -> list[CitationSnapshotRecord]:
        """Load citation snapshots and URLs for a run."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM citation_snapshots WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
            results: list[CitationSnapshotRecord] = []
            for row in rows:
                url_rows = conn.execute(
                    """
                    SELECT citation_url, citation_position
                    FROM citation_snapshot_urls
                    WHERE snapshot_id = ?
                    ORDER BY citation_position ASC
                    """,
                    (int(row["id"]),),
                ).fetchall()
                results.append(
                    CitationSnapshotRecord(
                        snapshot_id=int(row["id"]),
                        provider=row["provider"],
                        model=row["model_name"],
                        prompt_id=int(row["prompt_id"] or 0),
                        prompt_text=row["prompt_text"],
                        task=row["task"],
                        task_confidence=float(row["task_confidence"]),
                        answer_text=row["answer_text"],
                        recorded_at=row["recorded_at"],
                        cited_urls=[u["citation_url"] for u in url_rows],
                        citation_positions=[int(u["citation_position"]) for u in url_rows],
                    )
                )
        return results

    def get_competitor_mentions_for_run(self, run_id: int) -> list[CompetitorMentionRecord]:
        """Load all competitor mentions linked to snapshots in a run."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*
                FROM competitor_mentions m
                JOIN citation_snapshots s ON s.id = m.snapshot_id
                WHERE s.run_id = ?
                """,
                (run_id,),
            ).fetchall()
        return [
            CompetitorMentionRecord(
                mention_id=int(row["id"]),
                snapshot_id=int(row["snapshot_id"]),
                competitor_domain=row["competitor_domain"],
                competitor_name=row["competitor_name"],
                cited=bool(row["cited"]),
                mentioned=bool(row["mentioned"]),
                position=int(row["position"]),
                sentiment=row["sentiment"],
            )
            for row in rows
        ]

    def get_benchmark_run(self, run_id: int) -> BenchmarkRunRecord | None:
        """Fetch a single benchmark run."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM benchmark_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        breakdown_raw = json.loads(row["breakdown_json"])
        breakdown = BenchmarkScoreBreakdown(**breakdown_raw)
        return BenchmarkRunRecord(
            run_id=int(row["id"]),
            domain=row["domain"],
            run_at=row["run_at"],
            schedule=row["schedule"],
            benchmark_score=int(row["benchmark_score"]),
            band=row["band"],
            breakdown=breakdown,
            provider_coverage=json.loads(row["provider_coverage_json"]),
        )

    def list_benchmark_runs(self, domain: str, limit: int = 20) -> list[BenchmarkRunRecord]:
        """List recent runs for a domain."""
        normalized = normalize_benchmark_domain(domain)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM benchmark_runs
                WHERE domain = ?
                ORDER BY run_at DESC, id DESC
                LIMIT ?
                """,
                (normalized, limit),
            ).fetchall()
        results: list[BenchmarkRunRecord] = []
        for row in rows:
            breakdown_raw = json.loads(row["breakdown_json"])
            results.append(
                BenchmarkRunRecord(
                    run_id=int(row["id"]),
                    domain=row["domain"],
                    run_at=row["run_at"],
                    schedule=row["schedule"],
                    benchmark_score=int(row["benchmark_score"]),
                    band=row["band"],
                    breakdown=BenchmarkScoreBreakdown(**breakdown_raw),
                    provider_coverage=json.loads(row["provider_coverage_json"]),
                )
            )
        return results

    def get_latest_citation_share_summary(self, domain: str) -> CitationShareSummary | None:
        """Return the latest AI-answer monitoring summary for a domain."""
        runs = self.list_benchmark_runs(domain, limit=1)
        if not runs:
            return None
        run = runs[0]
        return build_citation_share_summary(
            run,
            self.get_snapshots_for_run(run.run_id),
            self.get_competitor_mentions_for_run(run.run_id),
        )

    def get_schedule(self, domain: str) -> BenchmarkScheduleRecord | None:
        """Fetch schedule for a domain if present."""
        normalized = normalize_benchmark_domain(domain)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark_schedules WHERE domain = ?",
                (normalized,),
            ).fetchone()
        if row is None:
            return None
        return BenchmarkScheduleRecord(
            schedule_id=int(row["id"]),
            domain=row["domain"],
            frequency=row["frequency"],
            competitor_domains=json.loads(row["competitor_domains_json"]),
            last_run_at=row["last_run_at"],
            next_run_at=row["next_run_at"],
            enabled=bool(row["enabled"]),
        )

    def update_schedule_run_times(
        self,
        domain: str,
        *,
        last_run_at: str,
        next_run_at: str | None,
    ) -> BenchmarkScheduleRecord | None:
        """Update last/next run timestamps for a schedule."""
        normalized = normalize_benchmark_domain(domain)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE benchmark_schedules
                SET last_run_at = ?, next_run_at = ?
                WHERE domain = ?
                """,
                (last_run_at, next_run_at, normalized),
            )
        return self.get_schedule(normalized)

    def upsert_schedule(
        self,
        domain: str,
        frequency: str,
        competitor_domains: list[str],
        *,
        enabled: bool = True,
    ) -> BenchmarkScheduleRecord:
        """Create or update a benchmark schedule for a domain."""
        normalized = normalize_benchmark_domain(domain)
        competitors_json = json.dumps([normalize_benchmark_domain(item) for item in competitor_domains])
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM benchmark_schedules WHERE domain = ?",
                (normalized,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE benchmark_schedules
                    SET frequency = ?, competitor_domains_json = ?, enabled = ?
                    WHERE domain = ?
                    """,
                    (frequency, competitors_json, 1 if enabled else 0, normalized),
                )
                schedule_id = int(existing["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO benchmark_schedules (
                        domain, frequency, competitor_domains_json, enabled
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (normalized, frequency, competitors_json, 1 if enabled else 0),
                )
                schedule_id = int(cursor.lastrowid or 0)
        return BenchmarkScheduleRecord(
            schedule_id=schedule_id,
            domain=normalized,
            frequency=frequency,
            competitor_domains=json.loads(competitors_json),
            enabled=enabled,
        )

    def prune_old_runs(self, retention_days: int = DEFAULT_BENCHMARK_RETENTION_DAYS) -> int:
        """Delete benchmark data older than retention window."""
        cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._connect() as conn:
            old_runs = conn.execute(
                "SELECT id FROM benchmark_runs WHERE run_at < ?",
                (cutoff_iso,),
            ).fetchall()
            run_ids = [int(row["id"]) for row in old_runs]
            if not run_ids:
                return 0
            placeholders = ",".join("?" * len(run_ids))
            conn.execute(f"DELETE FROM evidence_artifacts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM page_task_coverage WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(
                f"""
                DELETE FROM competitor_mentions
                WHERE snapshot_id IN (
                    SELECT id FROM citation_snapshots WHERE run_id IN ({placeholders})
                )
                """,
                run_ids,
            )
            conn.execute(
                f"""
                DELETE FROM citation_snapshot_urls
                WHERE snapshot_id IN (
                    SELECT id FROM citation_snapshots WHERE run_id IN ({placeholders})
                )
                """,
                run_ids,
            )
            conn.execute(
                f"DELETE FROM citation_snapshots WHERE run_id IN ({placeholders})",
                run_ids,
            )
            conn.execute(f"DELETE FROM benchmark_runs WHERE id IN ({placeholders})", run_ids)
        return len(run_ids)

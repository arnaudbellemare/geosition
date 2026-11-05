"""SQLite persistence for GEO platform tenants."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import SupportsIndex, SupportsInt, Union, cast
from urllib.parse import urlparse

from geo_optimizer.models.config import PLATFORM_SESSION_DAYS
from geo_optimizer.saas.models import (
    AgentUsageEvent,
    IndexTelemetrySummary,
    IndexTrendPoint,
    Organization,
    OrgBenchmarkLink,
    OrgCompetitor,
    OrgPrompt,
    PageAuditRecord,
    PlatformRun,
    PlatformUser,
    SessionInfo,
    VerifiedDomain,
    WeeklyEvidenceMetric,
    WeeklyEvidenceRun,
)
from geo_optimizer.storage.paths import resolve_platform_db_path

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_REQUIRED_SQLITE_TABLES = (
    "platform_users",
    "organizations",
    "memberships",
    "sessions",
    "password_reset_tokens",
    "verified_domains",
    "org_competitors",
    "org_prompts",
    "org_benchmark_runs",
    "platform_runs",
    "page_audits",
    "weekly_evidence_runs",
    "agent_usage_events",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_domain(domain: str) -> str:
    raw = domain.strip().lower()
    if raw.startswith(("http://", "https://")):
        return (urlparse(raw).hostname or raw).lower()
    return raw.split("/")[0].split(":")[0]


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:48] or "org"


def _prompt_external_id(query_text: str) -> str:
    """Stable generated prompt id for stores that upsert on external_id."""
    normalized = " ".join(query_text.strip().lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"p{digest}"


_IntInput = Union[str, bytes, bytearray, SupportsInt, SupportsIndex]


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(cast(_IntInput, value))
    except (TypeError, ValueError):
        return None


class PlatformStore:
    """Tenant store for users, orgs, domains, prompts, and benchmark links."""

    def __init__(self, db_path: Path | None = None):
        env_path = os.environ.get("GEO_PLATFORM_DB")
        self.db_path = db_path or (Path(env_path) if env_path else resolve_platform_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save_search_connection(self, org_id: int, domain: str, provider: str, property_id: str, encrypted: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO search_connections (org_id, domain, provider, property_id, encrypted_refresh_token)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT(org_id, domain, provider) DO UPDATE SET
                   property_id=excluded.property_id, encrypted_refresh_token=excluded.encrypted_refresh_token,
                   status='connected', last_synced_at=NULL, last_result_json='{}'""",
                (org_id, domain, provider, property_id, encrypted),
            )

    def list_search_connections(self, org_id: int | None = None) -> list[dict]:
        with self._connect() as conn:
            if org_id is None:
                rows = conn.execute("SELECT * FROM search_connections ORDER BY last_synced_at LIMIT 100").fetchall()
            else:
                rows = conn.execute("SELECT * FROM search_connections WHERE org_id=?", (org_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_search_connection(self, org_id: int, domain: str, provider: str, values: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE search_connections SET status=?, last_synced_at=?, last_result_json=?,
                   encrypted_refresh_token=? WHERE org_id=? AND domain=? AND provider=?""",
                (
                    values["status"],
                    values["last_synced_at"],
                    values["last_result_json"],
                    values["encrypted_refresh_token"],
                    org_id,
                    domain,
                    provider,
                ),
            )

    def delete_search_connection(self, org_id: int, domain: str, provider: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM search_connections WHERE org_id=? AND domain=? AND provider=?", (org_id, domain, provider)
            )

    def mark_search_connection_error(self, org_id: int, domain: str, provider: str, at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE search_connections SET status='sync_error', last_synced_at=? "
                "WHERE org_id=? AND domain=? AND provider=?",
                (at, org_id, domain, provider),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def storage_health(self) -> dict[str, object]:
        """Return whether the local platform database has the expected feature tables."""
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        existing = {str(row["name"]) for row in rows}
        tables = [
            {
                "table": table,
                "ok": table in existing,
                "migration": "sqlite_init",
                "error": "" if table in existing else "Missing local SQLite table",
            }
            for table in _REQUIRED_SQLITE_TABLES
        ]
        return {
            "backend": "sqlite",
            "ok": all(bool(table["ok"]) for table in tables),
            "required_migrations": ["sqlite_init"],
            "missing_migrations": [],
            "tables": tables,
        }

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_connections (
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    property_id TEXT NOT NULL,
                    encrypted_refresh_token TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'connected',
                    last_synced_at TEXT,
                    last_result_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (org_id, domain, provider)
                );

                CREATE TABLE IF NOT EXISTS platform_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    email_domain TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email_domain TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memberships (
                    user_id INTEGER NOT NULL,
                    org_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'owner',
                    PRIMARY KEY (user_id, org_id),
                    FOREIGN KEY (user_id) REFERENCES platform_users(id) ON DELETE CASCADE,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES platform_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES platform_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS verified_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    verify_token TEXT NOT NULL,
                    verify_method TEXT NOT NULL DEFAULT 'dns',
                    verified_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (org_id, domain),
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS org_competitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    UNIQUE (org_id, domain),
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS org_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    external_id TEXT NOT NULL DEFAULT '',
                    query_text TEXT NOT NULL,
                    query_class TEXT NOT NULL DEFAULT '',
                    keyword_topic TEXT NOT NULL DEFAULT '',
                    persona TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL DEFAULT '',
                    UNIQUE (org_id, external_id),
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS org_benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    benchmark_run_id INTEGER NOT NULL,
                    benchmark_score INTEGER NOT NULL,
                    band TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS platform_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    score INTEGER,
                    band TEXT NOT NULL DEFAULT '',
                    external_run_id TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    result_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS page_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    sitemap_url TEXT NOT NULL DEFAULT '',
                    score INTEGER NOT NULL DEFAULT 0,
                    band TEXT NOT NULL DEFAULT '',
                    http_status INTEGER,
                    error TEXT NOT NULL DEFAULT '',
                    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
                    title_issues_json TEXT NOT NULL DEFAULT '[]',
                    meta_issues_json TEXT NOT NULL DEFAULT '[]',
                    schema_issues_json TEXT NOT NULL DEFAULT '[]',
                    recommendations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES platform_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS weekly_evidence_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    score INTEGER,
                    band TEXT NOT NULL DEFAULT '',
                    metrics_json TEXT NOT NULL DEFAULT '[]',
                    action_plan_json TEXT NOT NULL DEFAULT '{}',
                    artifact_json_uri TEXT NOT NULL DEFAULT '',
                    artifact_html_uri TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    generated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    page_url TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL,
                    agent TEXT NOT NULL DEFAULT '',
                    query_text TEXT NOT NULL DEFAULT '',
                    answer_excerpt TEXT NOT NULL DEFAULT '',
                    cited_url TEXT NOT NULL DEFAULT '',
                    cited_rank INTEGER,
                    surfaced INTEGER NOT NULL DEFAULT 0,
                    cited INTEGER NOT NULL DEFAULT 0,
                    top_recommendation INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    value_units REAL NOT NULL DEFAULT 0.0,
                    evidence_artifact_id TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
                CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens (user_id);
                CREATE INDEX IF NOT EXISTS idx_domains_org ON verified_domains (org_id);
                CREATE INDEX IF NOT EXISTS idx_platform_runs_org ON platform_runs (org_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_page_audits_org_domain
                    ON page_audits (org_id, domain, created_at);
                CREATE INDEX IF NOT EXISTS idx_page_audits_org_page
                    ON page_audits (org_id, page_url, created_at);
                CREATE INDEX IF NOT EXISTS idx_page_audits_run ON page_audits (run_id);
                CREATE INDEX IF NOT EXISTS idx_weekly_evidence_org_domain
                    ON weekly_evidence_runs (org_id, domain, generated_at);
                CREATE INDEX IF NOT EXISTS idx_agent_usage_org_domain
                    ON agent_usage_events (org_id, domain, created_at);
                """
            )
            self._ensure_column(conn, "agent_usage_events", "evidence_artifact_id", "TEXT NOT NULL DEFAULT ''")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        """Add a column for existing MVP SQLite databases when a migration is introduced."""
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_user(self, email: str, email_domain: str, password_hash: str) -> PlatformUser:
        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO platform_users (email, email_domain, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, email_domain, password_hash, created_at),
            )
            user_id = int(cursor.lastrowid or 0)
        return PlatformUser(user_id=user_id, email=email, email_domain=email_domain, created_at=created_at)

    def get_user_by_email(self, email: str) -> PlatformUser | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM platform_users WHERE email = ?", (email,)).fetchone()
        return self._row_user(row) if row else None

    def get_user_by_id(self, user_id: int) -> PlatformUser | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM platform_users WHERE id = ?", (user_id,)).fetchone()
        return self._row_user(row) if row else None

    def delete_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM platform_users WHERE id = ?", (user_id,))

    def get_password_hash(self, user_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT password_hash FROM platform_users WHERE id = ?", (user_id,)).fetchone()
        return str(row["password_hash"]) if row else None

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE platform_users SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def create_password_reset_token(self, user_id: int, token_hash: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
                (_now_iso(), user_id),
            )
            conn.execute(
                """
                INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, user_id, expires_at, _now_iso()),
            )

    def get_password_reset_token(self, token_hash: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM password_reset_tokens
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (token_hash, _now_iso()),
            ).fetchone()
        return dict(row) if row else None

    def mark_password_reset_token_used(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
                (_now_iso(), token_hash),
            )

    def delete_sessions_for_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def create_organization(self, *, name: str, email_domain: str, owner_user_id: int) -> Organization:
        created_at = _now_iso()
        slug_base = _slugify(email_domain)
        with self._connect() as conn:
            slug = slug_base
            suffix = 0
            while conn.execute("SELECT 1 FROM organizations WHERE slug = ?", (slug,)).fetchone():
                suffix += 1
                slug = f"{slug_base}-{suffix}"
            cursor = conn.execute(
                """
                INSERT INTO organizations (name, email_domain, slug, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, email_domain, slug, created_at),
            )
            org_id = int(cursor.lastrowid or 0)
            conn.execute(
                "INSERT INTO memberships (user_id, org_id, role) VALUES (?, ?, 'owner')",
                (owner_user_id, org_id),
            )
        return Organization(org_id=org_id, name=name, email_domain=email_domain, slug=slug, created_at=created_at)

    def get_primary_org_for_user(self, user_id: int) -> Organization | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT o.* FROM organizations o
                JOIN memberships m ON m.org_id = o.id
                WHERE m.user_id = ?
                ORDER BY m.role = 'owner' DESC, o.id ASC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._row_org(row) if row else None

    def create_session(self, user_id: int, token: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user_id, expires_at, _now_iso()),
            )

    def create_worker_session(self, org_id: int) -> SessionInfo:
        """Create a short-lived internal session for a claimed worker run."""
        expires = (datetime.now(timezone.utc) + timedelta(days=min(1, PLATFORM_SESSION_DAYS))).isoformat()
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id FROM memberships
                WHERE org_id = ?
                ORDER BY role = 'owner' DESC, user_id ASC
                LIMIT 1
                """,
                (org_id,),
            ).fetchone()
            if row is None:
                raise ValueError("No workspace owner found for queued run")
            user_id = int(row["user_id"])
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user_id, expires, _now_iso()),
            )
        return SessionInfo(token=token, user_id=user_id, expires_at=expires)

    def get_session(self, token: str) -> SessionInfo | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if row is None:
            return None
        return SessionInfo(token=row["token"], user_id=int(row["user_id"]), expires_at=row["expires_at"])

    def delete_session(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def add_domain(self, org_id: int, domain: str, verify_token: str) -> VerifiedDomain:
        normalized = _normalize_domain(domain)
        email_domain = self._org_email_domain(org_id)
        if normalized != email_domain and not normalized.endswith("." + email_domain):
            pass  # allow www or subdomains after verify — still allow add; verify proves control
        created_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO verified_domains (
                    org_id, domain, status, verify_token, verify_method, created_at
                ) VALUES (?, ?, 'pending', ?, 'dns', ?)
                ON CONFLICT(org_id, domain) DO UPDATE SET verify_token = excluded.verify_token
                """,
                (org_id, normalized, verify_token, created_at),
            )
            row = conn.execute(
                "SELECT * FROM verified_domains WHERE org_id = ? AND domain = ?",
                (org_id, normalized),
            ).fetchone()
        return self._row_domain(row)

    def _org_email_domain(self, org_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT email_domain FROM organizations WHERE id = ?", (org_id,)).fetchone()
        return str(row["email_domain"]) if row else ""

    def list_domains(self, org_id: int) -> list[VerifiedDomain]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM verified_domains WHERE org_id = ? ORDER BY id ASC",
                (org_id,),
            ).fetchall()
        return [self._row_domain(row) for row in rows]

    def get_domain(self, domain_id: int, org_id: int) -> VerifiedDomain | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM verified_domains WHERE id = ? AND org_id = ?",
                (domain_id, org_id),
            ).fetchone()
        return self._row_domain(row) if row else None

    def mark_domain_verified(self, domain_id: int, *, method: str) -> VerifiedDomain | None:
        verified_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE verified_domains
                SET status = 'verified', verify_method = ?, verified_at = ?
                WHERE id = ?
                """,
                (method, verified_at, domain_id),
            )
            row = conn.execute("SELECT * FROM verified_domains WHERE id = ?", (domain_id,)).fetchone()
        return self._row_domain(row) if row else None

    def add_competitor(self, org_id: int, domain: str) -> OrgCompetitor:
        normalized = _normalize_domain(domain)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO org_competitors (org_id, domain) VALUES (?, ?)",
                (org_id, normalized),
            )
            if cursor.lastrowid:
                comp_id = int(cursor.lastrowid)
            else:
                row = conn.execute(
                    "SELECT id FROM org_competitors WHERE org_id = ? AND domain = ?",
                    (org_id, normalized),
                ).fetchone()
                comp_id = int(row["id"])
        return OrgCompetitor(competitor_id=comp_id, org_id=org_id, domain=normalized)

    def list_competitors(self, org_id: int) -> list[OrgCompetitor]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM org_competitors WHERE org_id = ? ORDER BY domain ASC",
                (org_id,),
            ).fetchall()
        return [OrgCompetitor(competitor_id=int(r["id"]), org_id=org_id, domain=r["domain"]) for r in rows]

    def add_prompt(
        self,
        org_id: int,
        *,
        external_id: str,
        query_text: str,
        query_class: str = "",
        keyword_topic: str = "",
        persona: str = "",
        country: str = "",
    ) -> OrgPrompt:
        ext = external_id or _prompt_external_id(query_text)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO org_prompts (
                    org_id, external_id, query_text, query_class,
                    keyword_topic, persona, country
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(org_id, external_id) DO UPDATE SET
                    query_text = excluded.query_text,
                    query_class = excluded.query_class
                """,
                (org_id, ext, query_text, query_class, keyword_topic, persona, country),
            )
            if cursor.lastrowid:
                pid = int(cursor.lastrowid)
            else:
                row = conn.execute(
                    "SELECT id FROM org_prompts WHERE org_id = ? AND external_id = ?",
                    (org_id, ext),
                ).fetchone()
                pid = int(row["id"])
        return OrgPrompt(
            prompt_id=pid,
            org_id=org_id,
            external_id=ext,
            query_text=query_text,
            query_class=query_class,
            keyword_topic=keyword_topic,
            persona=persona,
            country=country,
        )

    def list_prompts(self, org_id: int) -> list[OrgPrompt]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM org_prompts WHERE org_id = ? ORDER BY id ASC",
                (org_id,),
            ).fetchall()
        return [self._row_prompt(row) for row in rows]

    def link_benchmark_run(
        self,
        org_id: int,
        *,
        domain: str,
        benchmark_run_id: int,
        benchmark_score: int,
        band: str,
        run_at: str,
    ) -> OrgBenchmarkLink:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO org_benchmark_runs (
                    org_id, domain, benchmark_run_id, benchmark_score, band, run_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (org_id, _normalize_domain(domain), benchmark_run_id, benchmark_score, band, run_at),
            )
            link_id = int(cursor.lastrowid or 0)
        return OrgBenchmarkLink(
            link_id=link_id,
            org_id=org_id,
            domain=_normalize_domain(domain),
            benchmark_run_id=benchmark_run_id,
            benchmark_score=benchmark_score,
            band=band,
            run_at=run_at,
        )

    def list_benchmark_runs(self, org_id: int, limit: int = 12) -> list[OrgBenchmarkLink]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM org_benchmark_runs
                WHERE org_id = ?
                ORDER BY run_at DESC, id DESC
                LIMIT ?
                """,
                (org_id, limit),
            ).fetchall()
        return [
            OrgBenchmarkLink(
                link_id=int(r["id"]),
                org_id=org_id,
                domain=r["domain"],
                benchmark_run_id=int(r["benchmark_run_id"]),
                benchmark_score=int(r["benchmark_score"]),
                band=r["band"],
                run_at=r["run_at"],
            )
            for r in rows
        ]

    def create_run(
        self,
        org_id: int,
        *,
        kind: str,
        domain: str,
        status: str = "queued",
        result_summary: str = "",
    ) -> PlatformRun:
        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO platform_runs (org_id, kind, domain, status, result_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (org_id, kind, _normalize_domain(domain), status, result_summary, created_at),
            )
            run_id = int(cursor.lastrowid or 0)
        return PlatformRun(
            run_id=run_id,
            org_id=org_id,
            kind=kind,
            domain=_normalize_domain(domain),
            status=status,
            result_summary=result_summary,
            created_at=created_at,
        )

    def mark_run_running(self, run_id: int, org_id: int) -> PlatformRun | None:
        started_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE platform_runs
                SET status = 'running', started_at = ?
                WHERE id = ? AND org_id = ? AND status IN ('queued', 'running')
                """,
                (started_at, run_id, org_id),
            )
            row = conn.execute("SELECT * FROM platform_runs WHERE id = ? AND org_id = ?", (run_id, org_id)).fetchone()
        return self._row_run(row) if row else None

    def claim_next_run(self, *, kind: str = "collection", domain: str = "") -> PlatformRun | None:
        """Atomically claim the oldest queued run for a hosted worker."""
        started_at = _now_iso()
        normalized = _normalize_domain(domain) if domain else ""
        with self._connect() as conn:
            params: list[object] = [kind]
            domain_filter = ""
            if normalized:
                domain_filter = "AND domain = ?"
                params.append(normalized)
            row = conn.execute(
                f"""
                SELECT * FROM platform_runs
                WHERE kind = ? AND status = 'queued' {domain_filter}
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
            if row is None:
                return None
            run_id = int(row["id"])
            cursor = conn.execute(
                """
                UPDATE platform_runs
                SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (started_at, run_id),
            )
            if cursor.rowcount != 1:
                return None
            claimed = conn.execute("SELECT * FROM platform_runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_run(claimed) if claimed else None

    def complete_run(
        self,
        run_id: int,
        org_id: int,
        *,
        score: int | None = None,
        band: str = "",
        external_run_id: str = "",
        result_summary: str = "",
    ) -> PlatformRun | None:
        completed_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE platform_runs
                SET status = 'completed',
                    score = ?,
                    band = ?,
                    external_run_id = ?,
                    error = '',
                    result_summary = ?,
                    completed_at = ?
                WHERE id = ? AND org_id = ?
                """,
                (score, band, external_run_id, result_summary, completed_at, run_id, org_id),
            )
            row = conn.execute("SELECT * FROM platform_runs WHERE id = ? AND org_id = ?", (run_id, org_id)).fetchone()
        return self._row_run(row) if row else None

    def fail_run(self, run_id: int, org_id: int, *, error: str) -> PlatformRun | None:
        completed_at = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE platform_runs
                SET status = 'failed',
                    error = ?,
                    completed_at = ?
                WHERE id = ? AND org_id = ?
                """,
                (error[:1000], completed_at, run_id, org_id),
            )
            row = conn.execute("SELECT * FROM platform_runs WHERE id = ? AND org_id = ?", (run_id, org_id)).fetchone()
        return self._row_run(row) if row else None

    def list_runs(self, org_id: int, *, limit: int = 12, kind: str = "") -> list[PlatformRun]:
        params: list[object] = [org_id]
        kind_filter = ""
        if kind:
            kind_filter = "AND kind = ?"
            params.append(kind)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM platform_runs
                WHERE org_id = ?
                {kind_filter}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_run(row) for row in rows]

    def replace_page_audits(
        self,
        org_id: int,
        *,
        run_id: int,
        domain: str,
        sitemap_url: str,
        pages: list[dict[str, object]],
    ) -> list[PageAuditRecord]:
        """Replace the page audit rows for one run with normalized durable rows."""
        created_at = _now_iso()
        normalized = _normalize_domain(domain)
        with self._connect() as conn:
            conn.execute("DELETE FROM page_audits WHERE org_id = ? AND run_id = ?", (org_id, run_id))
            inserted_ids: list[int] = []
            for page in pages:
                cursor = conn.execute(
                    """
                    INSERT INTO page_audits (
                        org_id, run_id, domain, page_url, sitemap_url, score, band, http_status, error,
                        score_breakdown_json, title_issues_json, meta_issues_json, schema_issues_json,
                        recommendations_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        org_id,
                        run_id,
                        normalized,
                        str(page.get("page_url") or page.get("url") or "")[:1000],
                        sitemap_url[:1000],
                        int(cast(_IntInput, page.get("score") or 0)),
                        str(page.get("band") or "")[:64],
                        _int_or_none(page.get("http_status")),
                        str(page.get("error") or "")[:1000],
                        json.dumps(page.get("score_breakdown") or {}, ensure_ascii=False, default=str)[:8000],
                        json.dumps(page.get("title_issues") or [], ensure_ascii=False, default=str)[:4000],
                        json.dumps(page.get("meta_issues") or [], ensure_ascii=False, default=str)[:4000],
                        json.dumps(page.get("schema_issues") or [], ensure_ascii=False, default=str)[:4000],
                        json.dumps(page.get("recommendations") or [], ensure_ascii=False, default=str)[:8000],
                        created_at,
                    ),
                )
                inserted_ids.append(int(cursor.lastrowid or 0))
            if not inserted_ids:
                return []
            placeholders = ",".join("?" for _ in inserted_ids)
            rows = conn.execute(
                f"SELECT * FROM page_audits WHERE id IN ({placeholders}) ORDER BY id ASC",
                tuple(inserted_ids),
            ).fetchall()
        return [self._with_page_history(record) for record in [self._row_page_audit(row) for row in rows]]

    def list_page_audits(
        self,
        org_id: int,
        *,
        domain: str = "",
        run_id: int | None = None,
        limit: int = 100,
    ) -> list[PageAuditRecord]:
        """List latest page audit records for an org/domain, or records for a specific run."""
        params: list[object] = [org_id]
        where = "org_id = ?"
        if domain:
            where += " AND domain = ?"
            params.append(_normalize_domain(domain))
        if run_id is not None:
            where += " AND run_id = ?"
            params.append(run_id)
            query = f"SELECT * FROM page_audits WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ?"
            params.append(limit)
        else:
            query = f"""
                SELECT pa.* FROM page_audits pa
                JOIN (
                    SELECT page_url, MAX(id) AS max_id
                    FROM page_audits
                    WHERE {where}
                    GROUP BY page_url
                ) latest ON latest.max_id = pa.id
                ORDER BY pa.created_at DESC, pa.id DESC
                LIMIT ?
            """
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._with_page_history(self._row_page_audit(row)) for row in rows]

    def page_audit_history(self, org_id: int, *, page_url: str, limit: int = 12) -> list[PageAuditRecord]:
        """Return score history for one audited URL."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM page_audits
                WHERE org_id = ? AND page_url = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (org_id, page_url, limit),
            ).fetchall()
        records = [self._row_page_audit(row) for row in rows]
        return [self._with_page_history(record) for record in records]

    def create_weekly_evidence_run(
        self,
        org_id: int,
        *,
        domain: str,
        period_start: str,
        period_end: str,
        status: str = "completed",
        score: int | None = None,
        band: str = "",
        metrics: list[WeeklyEvidenceMetric] | None = None,
        artifact_json_uri: str = "",
        artifact_html_uri: str = "",
        summary: str = "",
        action_plan: dict[str, object] | None = None,
        generated_at: str = "",
    ) -> WeeklyEvidenceRun:
        """Persist one weekly evidence report snapshot."""
        created_at = _now_iso()
        generated = generated_at or created_at
        normalized = _normalize_domain(domain)
        metrics_payload = json.dumps([self._metric_to_dict(metric) for metric in (metrics or [])], default=str)
        action_payload = json.dumps(action_plan or {}, default=str)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO weekly_evidence_runs (
                    org_id, domain, period_start, period_end, status, score, band,
                    metrics_json, action_plan_json, artifact_json_uri, artifact_html_uri,
                    summary, generated_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    org_id,
                    normalized,
                    period_start,
                    period_end,
                    status,
                    score,
                    band,
                    metrics_payload,
                    action_payload,
                    artifact_json_uri,
                    artifact_html_uri,
                    summary[:2000],
                    generated,
                    created_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM weekly_evidence_runs WHERE id = ? AND org_id = ?",
                (int(cursor.lastrowid or 0), org_id),
            ).fetchone()
        return self._row_weekly_evidence_run(row)

    def complete_weekly_evidence_run(
        self,
        report_id: int,
        org_id: int,
        *,
        status: str = "completed",
        score: int | None = None,
        band: str = "",
        metrics: list[WeeklyEvidenceMetric] | None = None,
        artifact_json_uri: str = "",
        artifact_html_uri: str = "",
        summary: str = "",
        action_plan: dict[str, object] | None = None,
    ) -> WeeklyEvidenceRun | None:
        """Update a weekly report with final metrics and artifact URIs."""
        metrics_payload = json.dumps([self._metric_to_dict(metric) for metric in (metrics or [])], default=str)
        action_payload = json.dumps(action_plan or {}, default=str)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE weekly_evidence_runs
                SET status = ?,
                    score = ?,
                    band = ?,
                    metrics_json = ?,
                    action_plan_json = ?,
                    artifact_json_uri = ?,
                    artifact_html_uri = ?,
                    summary = ?
                WHERE id = ? AND org_id = ?
                """,
                (
                    status,
                    score,
                    band,
                    metrics_payload,
                    action_payload,
                    artifact_json_uri,
                    artifact_html_uri,
                    summary[:2000],
                    report_id,
                    org_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM weekly_evidence_runs WHERE id = ? AND org_id = ?",
                (report_id, org_id),
            ).fetchone()
        return self._row_weekly_evidence_run(row) if row else None

    def list_weekly_evidence_runs(
        self,
        org_id: int,
        *,
        domain: str = "",
        limit: int = 12,
    ) -> list[WeeklyEvidenceRun]:
        """List recent weekly evidence reports."""
        params: list[object] = [org_id]
        domain_filter = ""
        if domain:
            domain_filter = "AND domain = ?"
            params.append(_normalize_domain(domain))
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM weekly_evidence_runs
                WHERE org_id = ?
                {domain_filter}
                ORDER BY generated_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_weekly_evidence_run(row) for row in rows]

    def get_latest_weekly_evidence_run(self, org_id: int, *, domain: str = "") -> WeeklyEvidenceRun | None:
        """Return the latest weekly evidence report for an org/domain."""
        rows = self.list_weekly_evidence_runs(org_id, domain=domain, limit=1)
        return rows[0] if rows else None

    def record_agent_usage_event(
        self,
        org_id: int,
        *,
        domain: str,
        page_url: str = "",
        source_type: str,
        agent: str = "",
        query: str = "",
        answer_excerpt: str = "",
        cited_url: str = "",
        cited_rank: int | None = None,
        surfaced: bool = False,
        cited: bool = False,
        top_recommendation: bool = False,
        confidence: float = 1.0,
        value_units: float = 0.0,
        evidence_artifact_id: str = "",
        evidence: dict[str, object] | None = None,
    ) -> AgentUsageEvent:
        """Persist one demand-side AI usage observation."""
        created_at = _now_iso()
        evidence_json = json.dumps(evidence or {}, ensure_ascii=False, default=str)[:4000]
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_usage_events (
                    org_id, domain, page_url, source_type, agent, query_text,
                    answer_excerpt, cited_url, cited_rank, surfaced, cited,
                    top_recommendation, confidence, value_units, evidence_json,
                    evidence_artifact_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    org_id,
                    _normalize_domain(domain),
                    page_url[:1000],
                    source_type[:64],
                    agent[:120],
                    query[:1000],
                    answer_excerpt[:4000],
                    cited_url[:1000],
                    cited_rank,
                    1 if surfaced else 0,
                    1 if cited else 0,
                    1 if top_recommendation else 0,
                    confidence,
                    value_units,
                    evidence_json,
                    evidence_artifact_id[:160],
                    created_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM agent_usage_events WHERE id = ?",
                (int(cursor.lastrowid or 0),),
            ).fetchone()
        return self._row_agent_usage_event(row)

    def list_agent_usage_events(
        self,
        org_id: int,
        *,
        domain: str = "",
        limit: int = 50,
    ) -> list[AgentUsageEvent]:
        params: list[object] = [org_id]
        domain_filter = ""
        if domain:
            domain_filter = "AND domain = ?"
            params.append(_normalize_domain(domain))
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM agent_usage_events
                WHERE org_id = ?
                {domain_filter}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_agent_usage_event(row) for row in rows]

    def index_summary(self, org_id: int, *, domain: str = "") -> IndexTelemetrySummary:
        """Aggregate agent usage into the content-owner Index view."""
        normalized = _normalize_domain(domain) if domain else ""
        events = self.list_agent_usage_events(org_id, domain=normalized, limit=1000)
        if not events:
            return IndexTelemetrySummary(domain=normalized, action_plan=self._index_action_plan([]))

        citation_events = [event for event in events if self._is_answer_visibility_source(event)]
        denominator = len(citation_events) or len(events)
        surfaced = sum(1 for event in events if event.surfaced)
        cited = sum(1 for event in citation_events if event.cited)
        top = sum(1 for event in citation_events if event.top_recommendation)
        value = round(sum(event.value_units for event in events), 2)
        return IndexTelemetrySummary(
            domain=normalized or events[0].domain,
            total_events=len(events),
            surfaced_events=surfaced,
            cited_events=cited,
            top_recommendation_events=top,
            citation_rate=round(cited / denominator, 4),
            top_recommendation_rate=round(top / denominator, 4),
            total_value_units=value,
            agent_coverage=self._count_by(events, "agent"),
            source_coverage=self._count_by(events, "source_type"),
            top_queries=self._count_by(events, "query"),
            top_pages=self._count_by(events, "page_url"),
            top_cited_pages=self._count_by([event for event in events if event.cited], "cited_url"),
            missed_queries=self._count_missed_queries(events),
            trend_points=self._trend_points(events),
            action_plan=self._index_action_plan(events),
            recent_events=events[:12],
        )

    def domain_claim_status(self, domain: str) -> dict[str, object]:
        """Return a privacy-light public claim status for a domain preview."""
        normalized = _normalize_domain(domain)
        variants = {normalized}
        if normalized.startswith("www."):
            variants.add(normalized[4:])
        else:
            variants.add(f"www.{normalized}")
        placeholders = ",".join("?" for _ in variants)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT status FROM verified_domains WHERE domain IN ({placeholders})",
                tuple(sorted(variants)),
            ).fetchall()
        statuses = [str(row["status"]) for row in rows]
        return {
            "domain": normalized,
            "claimed": bool(statuses),
            "verified": any(status == "verified" for status in statuses),
        }

    def _row_user(self, row: sqlite3.Row) -> PlatformUser:
        return PlatformUser(
            user_id=int(row["id"]),
            email=row["email"],
            email_domain=row["email_domain"],
            created_at=row["created_at"],
        )

    def _row_org(self, row: sqlite3.Row) -> Organization:
        return Organization(
            org_id=int(row["id"]),
            name=row["name"],
            email_domain=row["email_domain"],
            slug=row["slug"],
            created_at=row["created_at"],
        )

    def _row_domain(self, row: sqlite3.Row) -> VerifiedDomain:
        return VerifiedDomain(
            domain_id=int(row["id"]),
            org_id=int(row["org_id"]),
            domain=row["domain"],
            status=row["status"],
            verify_token=row["verify_token"],
            verify_method=row["verify_method"] or "",
            verified_at=row["verified_at"],
            created_at=row["created_at"],
        )

    def _row_prompt(self, row: sqlite3.Row) -> OrgPrompt:
        return OrgPrompt(
            prompt_id=int(row["id"]),
            org_id=int(row["org_id"]),
            external_id=row["external_id"],
            query_text=row["query_text"],
            query_class=row["query_class"],
            keyword_topic=row["keyword_topic"],
            persona=row["persona"],
            country=row["country"],
        )

    def _row_run(self, row: sqlite3.Row) -> PlatformRun:
        return PlatformRun(
            run_id=int(row["id"]),
            org_id=int(row["org_id"]),
            kind=row["kind"],
            domain=row["domain"],
            status=row["status"],
            score=int(row["score"]) if row["score"] is not None else None,
            band=row["band"] or "",
            external_run_id=row["external_run_id"] or "",
            error=row["error"] or "",
            result_summary=row["result_summary"] or "",
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _row_page_audit(self, row: sqlite3.Row) -> PageAuditRecord:
        return PageAuditRecord(
            page_audit_id=int(row["id"]),
            org_id=int(row["org_id"]),
            run_id=int(row["run_id"]),
            domain=row["domain"],
            page_url=row["page_url"],
            sitemap_url=row["sitemap_url"] or "",
            score=int(row["score"] or 0),
            band=row["band"] or "",
            http_status=int(row["http_status"]) if row["http_status"] is not None else None,
            error=row["error"] or "",
            score_breakdown=self._loads_dict(row["score_breakdown_json"]),
            title_issues=self._loads_list(row["title_issues_json"]),
            meta_issues=self._loads_list(row["meta_issues_json"]),
            schema_issues=self._loads_list(row["schema_issues_json"]),
            recommendations=self._loads_list(row["recommendations_json"]),
            created_at=row["created_at"],
        )

    def _with_page_history(self, record: PageAuditRecord) -> PageAuditRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT score FROM page_audits
                WHERE org_id = ? AND page_url = ? AND id < ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (record.org_id, record.page_url, record.page_audit_id),
            ).fetchone()
        if row is None:
            return record
        previous = int(row["score"] or 0)
        record.previous_score = previous
        record.score_delta = record.score - previous
        return record

    def _row_weekly_evidence_run(self, row: sqlite3.Row) -> WeeklyEvidenceRun:
        try:
            metrics_raw = json.loads(row["metrics_json"] or "[]")
        except ValueError:
            metrics_raw = []
        try:
            action_plan = json.loads(row["action_plan_json"] or "{}")
        except ValueError:
            action_plan = {}
        metrics = [
            WeeklyEvidenceMetric(
                key=str(item.get("key", "")),
                label=str(item.get("label", "")),
                value=str(item.get("value", "")),
                previous_value=str(item.get("previous_value", "")),
                delta=str(item.get("delta", "")),
                unit=str(item.get("unit", "")),
                status=str(item.get("status", "unknown")),
                evidence_ref=str(item.get("evidence_ref", "")),
            )
            for item in metrics_raw
            if isinstance(item, dict)
        ]
        return WeeklyEvidenceRun(
            report_id=int(row["id"]),
            org_id=int(row["org_id"]),
            domain=row["domain"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            status=row["status"],
            generated_at=row["generated_at"],
            score=int(row["score"]) if row["score"] is not None else None,
            band=row["band"],
            metrics=metrics,
            artifact_json_uri=row["artifact_json_uri"],
            artifact_html_uri=row["artifact_html_uri"],
            summary=row["summary"],
            action_plan=action_plan if isinstance(action_plan, dict) else {},
        )

    def _row_agent_usage_event(self, row: sqlite3.Row) -> AgentUsageEvent:
        evidence: dict[str, object] = {}
        try:
            parsed = json.loads(row["evidence_json"] or "{}")
            if isinstance(parsed, dict):
                evidence = parsed
        except json.JSONDecodeError:
            evidence = {}
        return AgentUsageEvent(
            event_id=int(row["id"]),
            org_id=int(row["org_id"]),
            domain=row["domain"],
            page_url=row["page_url"] or "",
            source_type=row["source_type"],
            agent=row["agent"] or "",
            query=row["query_text"] or "",
            answer_excerpt=row["answer_excerpt"] or "",
            cited_url=row["cited_url"] or "",
            cited_rank=int(row["cited_rank"]) if row["cited_rank"] is not None else None,
            surfaced=bool(row["surfaced"]),
            cited=bool(row["cited"]),
            top_recommendation=bool(row["top_recommendation"]),
            confidence=float(row["confidence"]),
            value_units=float(row["value_units"]),
            evidence_artifact_id=row["evidence_artifact_id"] or "",
            evidence=evidence,
            created_at=row["created_at"],
        )

    @staticmethod
    def _loads_dict(raw: object) -> dict[str, object]:
        try:
            parsed = json.loads(str(raw or "{}"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _loads_list(raw: object) -> list[str]:
        try:
            parsed = json.loads(str(raw or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]

    @staticmethod
    def _metric_to_dict(metric: WeeklyEvidenceMetric) -> dict[str, object]:
        return {
            "key": metric.key,
            "label": metric.label,
            "value": metric.value,
            "previous_value": metric.previous_value,
            "delta": metric.delta,
            "unit": metric.unit,
            "status": metric.status,
            "evidence_ref": metric.evidence_ref,
        }

    @staticmethod
    def _count_by(events: list[AgentUsageEvent], attr: str, *, limit: int = 8) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            value = str(getattr(event, attr, "") or "").strip()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])

    @staticmethod
    def _count_missed_queries(events: list[AgentUsageEvent], *, limit: int = 8) -> dict[str, int]:
        missed = [event for event in events if event.query and not event.cited and not event.top_recommendation]
        return PlatformStore._count_by(missed, "query", limit=limit)

    @staticmethod
    def _trend_points(events: list[AgentUsageEvent], *, limit: int = 30) -> list[IndexTrendPoint]:
        buckets: dict[str, IndexTrendPoint] = {}
        for event in events:
            day = (event.created_at or "")[:10] or "unknown"
            bucket = buckets.setdefault(day, {"date": day, "events": 0, "cited": 0, "top": 0, "value_units": 0.0})
            bucket["events"] += 1
            bucket["cited"] += 1 if event.cited else 0
            bucket["top"] += 1 if event.top_recommendation else 0
            bucket["value_units"] = round(bucket["value_units"] + event.value_units, 2)
        return [buckets[day] for day in sorted(buckets)[-limit:]]

    @staticmethod
    def _is_answer_visibility_source(event: AgentUsageEvent) -> bool:
        """Return True for evidence sources that observe AI-answer citation position."""
        return event.source_type not in {"crawler_log", "retrieval_probe", "serp_check"}

    @staticmethod
    def _has_source(events: list[AgentUsageEvent], source_type: str) -> bool:
        return any(event.source_type == source_type for event in events)

    @staticmethod
    def _index_action_plan(events: list[AgentUsageEvent]) -> dict[str, object]:
        """Map observed answer/crawl evidence to the 2026 GEO decision loop."""
        base = {
            "source": "arXiv:2605.25517",
            "workflow": "top_recommendation -> cited -> retrieval_path_or_content_brief -> retest",
        }
        if not events:
            return {
                **base,
                "status": "no_evidence",
                "priority": "Collect AI answer evidence",
                "next_step": "Run a benchmark or paste an AI answer for target queries.",
                "fix_order": ["serp_check", "benchmark", "retrieval_probe", "content_brief"],
            }

        answer_events = [event for event in events if PlatformStore._is_answer_visibility_source(event)]
        if not answer_events:
            if PlatformStore._has_source(events, "serp_check"):
                return {
                    **base,
                    "status": "organic_visibility_seen",
                    "priority": "Convert search visibility into answer evidence",
                    "next_step": (
                        "Organic SERP position is being checked automatically; run an AI-answer benchmark next "
                        "to see whether that retrieval position becomes a citation."
                    ),
                    "fix_order": ["benchmark", "ai_answer_evidence", "retrieval_probe", "content_brief"],
                }
            return {
                **base,
                "status": "crawl_seen",
                "priority": "Measure answer visibility",
                "next_step": "AI crawlers reached the site; run SERP checks and answer benchmarks to see if the content is retrievable and cited.",
                "fix_order": ["serp_check", "benchmark", "retrieval_probe"],
            }

        latest = answer_events[0]
        if latest.top_recommendation:
            return {
                **base,
                "status": "top_recommendation",
                "priority": "Maintain and monitor",
                "next_step": "Top recommendation achieved. Re-test periodically and track value units over time.",
                "fix_order": ["monitor", "trend_delta"],
            }
        if latest.cited:
            return {
                **base,
                "status": "cited_not_top",
                "priority": "Fix content-brief gatekeepers first",
                "next_step": "The source is cited but not ranked first; fix gatekeepers before differentiators.",
                "fix_order": [
                    "topic_match",
                    "price_or_product_detail",
                    "freshness",
                    "top_list_position",
                    "comparisons",
                    "evidence",
                ],
            }
        return {
            **base,
            "status": "retrieval_gap",
            "priority": "Improve retrieval before content polish",
            "next_step": "The source is not cited; focus on crawlability, indexability, ranking, and retrieval probes first.",
            "fix_order": ["retrieval_path", "technical_seo", "indexability", "query_page_match"],
        }

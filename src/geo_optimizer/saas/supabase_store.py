"""Supabase PostgREST backend for GEOSITION Platform (production)."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import quote

import requests

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
from geo_optimizer.saas.store import _int_or_none, _IntInput, _normalize_domain, _prompt_external_id, _slugify

_TABLE_USERS = "geo_platform_users"
_TABLE_ORGS = "geo_organizations"
_TABLE_MEMBERSHIPS = "geo_memberships"
_TABLE_SESSIONS = "geo_sessions"
_TABLE_PASSWORD_RESETS = "geo_password_reset_tokens"
_TABLE_DOMAINS = "geo_verified_domains"
_TABLE_COMPETITORS = "geo_org_competitors"
_TABLE_PROMPTS = "geo_org_prompts"
_TABLE_BENCHMARKS = "geo_org_benchmark_runs"
_TABLE_RUNS = "geo_platform_runs"
_TABLE_PAGE_AUDITS = "geo_page_audits"
_TABLE_AGENT_USAGE = "geo_agent_usage_events"
_TABLE_WEEKLY_EVIDENCE = "geo_weekly_evidence_runs"
_REQUIRED_SUPABASE_TABLES = (
    (_TABLE_USERS, "002_geo_platform.sql"),
    (_TABLE_ORGS, "002_geo_platform.sql"),
    (_TABLE_MEMBERSHIPS, "002_geo_platform.sql"),
    (_TABLE_SESSIONS, "002_geo_platform.sql"),
    (_TABLE_PASSWORD_RESETS, "002_geo_platform.sql"),
    (_TABLE_DOMAINS, "002_geo_platform.sql"),
    (_TABLE_COMPETITORS, "002_geo_platform.sql"),
    (_TABLE_PROMPTS, "002_geo_platform.sql"),
    (_TABLE_BENCHMARKS, "002_geo_platform.sql"),
    (_TABLE_RUNS, "002_geo_platform.sql"),
    (_TABLE_AGENT_USAGE, "002_geo_platform.sql"),
    (_TABLE_PAGE_AUDITS, "004_platform_feature_storage_backfill.sql"),
    (_TABLE_WEEKLY_EVIDENCE, "004_platform_feature_storage_backfill.sql"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabasePlatformStore:
    """Platform persistence via Supabase REST (service role). Mirrors PlatformStore API."""

    def __init__(self) -> None:
        base = os.environ.get("SUPABASE_URL", os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")).rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not base or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase backend")
        self.base_url = f"{base}/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str = "return=representation",
    ) -> list[dict]:
        url = f"{self.base_url}/{table}"
        if params:
            query = "&".join(f"{quote(k)}={quote(v)}" for k, v in params.items())
            url = f"{url}?{query}"
        headers = {**self.headers, "Prefer": prefer}
        response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {table} failed: {response.status_code} {response.text[:300]}")
        if not response.text:
            return []
        data = response.json()
        return data if isinstance(data, list) else [data]

    def storage_health(self) -> dict[str, object]:
        """Check whether Supabase exposes every table required by the platform UI."""
        tables: list[dict[str, object]] = []
        for table, migration in _REQUIRED_SUPABASE_TABLES:
            try:
                self._request("GET", table, params={"select": "*", "limit": "0"})
            except RuntimeError as exc:
                tables.append(
                    {
                        "table": table,
                        "ok": False,
                        "migration": migration,
                        "error": str(exc)[:300],
                    }
                )
            else:
                tables.append({"table": table, "ok": True, "migration": migration, "error": ""})
        missing_migrations = sorted({str(table["migration"]) for table in tables if not table["ok"]})
        return {
            "backend": "supabase",
            "ok": not missing_migrations,
            "required_migrations": [
                "002_geo_platform.sql",
                "003_weekly_evidence_runs.sql",
                "004_platform_feature_storage_backfill.sql",
            ],
            "missing_migrations": missing_migrations,
            "tables": tables,
        }

    def create_user(self, email: str, email_domain: str, password_hash: str) -> PlatformUser:
        rows = self._request(
            "POST",
            _TABLE_USERS,
            json_body={"email": email, "email_domain": email_domain, "password_hash": password_hash},
        )
        row = rows[0]
        return PlatformUser(
            user_id=int(row["id"]),
            email=row["email"],
            email_domain=row["email_domain"],
            created_at=row["created_at"],
        )

    def get_user_by_email(self, email: str) -> PlatformUser | None:
        rows = self._request("GET", _TABLE_USERS, params={"email": f"eq.{email}", "limit": "1"})
        return self._row_user(rows[0]) if rows else None

    def get_user_by_id(self, user_id: int) -> PlatformUser | None:
        rows = self._request("GET", _TABLE_USERS, params={"id": f"eq.{user_id}", "limit": "1"})
        return self._row_user(rows[0]) if rows else None

    def delete_user(self, user_id: int) -> None:
        self._request("DELETE", _TABLE_USERS, params={"id": f"eq.{user_id}"}, prefer="return=minimal")

    def get_password_hash(self, user_id: int) -> str | None:
        rows = self._request(
            "GET",
            _TABLE_USERS,
            params={"id": f"eq.{user_id}", "select": "password_hash", "limit": "1"},
        )
        return str(rows[0]["password_hash"]) if rows else None

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        self._request(
            "PATCH",
            _TABLE_USERS,
            params={"id": f"eq.{user_id}"},
            json_body={"password_hash": password_hash},
            prefer="return=minimal",
        )

    def create_password_reset_token(self, user_id: int, token_hash: str, expires_at: str) -> None:
        self._request(
            "PATCH",
            _TABLE_PASSWORD_RESETS,
            params={"user_id": f"eq.{user_id}", "used_at": "is.null"},
            json_body={"used_at": _now_iso()},
            prefer="return=minimal",
        )
        self._request(
            "POST",
            _TABLE_PASSWORD_RESETS,
            json_body={"token_hash": token_hash, "user_id": user_id, "expires_at": expires_at},
            prefer="return=minimal",
        )

    def get_password_reset_token(self, token_hash: str) -> dict[str, object] | None:
        rows = self._request(
            "GET",
            _TABLE_PASSWORD_RESETS,
            params={
                "token_hash": f"eq.{token_hash}",
                "used_at": "is.null",
                "expires_at": f"gt.{_now_iso()}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def mark_password_reset_token_used(self, token_hash: str) -> None:
        self._request(
            "PATCH",
            _TABLE_PASSWORD_RESETS,
            params={"token_hash": f"eq.{token_hash}"},
            json_body={"used_at": _now_iso()},
            prefer="return=minimal",
        )

    def create_organization(self, *, name: str, email_domain: str, owner_user_id: int) -> Organization:
        slug_base = _slugify(email_domain)
        row = None
        last_error: RuntimeError | None = None
        for suffix in range(25):
            slug = slug_base if suffix == 0 else f"{slug_base}-{suffix}"
            try:
                rows = self._request(
                    "POST",
                    _TABLE_ORGS,
                    json_body={"name": name, "email_domain": email_domain, "slug": slug},
                )
                row = rows[0]
                break
            except RuntimeError as exc:
                last_error = exc
                message = str(exc).lower()
                if "duplicate" not in message and "23505" not in message:
                    raise
        if row is None:
            raise last_error or RuntimeError("Could not create unique organization slug")

        org_id = int(row["id"])
        try:
            self._request(
                "POST",
                _TABLE_MEMBERSHIPS,
                json_body={"user_id": owner_user_id, "org_id": org_id, "role": "owner"},
                prefer="return=minimal",
            )
        except RuntimeError:
            self._request("DELETE", _TABLE_ORGS, params={"id": f"eq.{org_id}"}, prefer="return=minimal")
            raise
        return Organization(
            org_id=org_id,
            name=row["name"],
            email_domain=row["email_domain"],
            slug=row["slug"],
            created_at=row["created_at"],
        )

    def get_primary_org_for_user(self, user_id: int) -> Organization | None:
        rows = self._request(
            "GET",
            _TABLE_MEMBERSHIPS,
            params={"user_id": f"eq.{user_id}", "select": "org_id,role", "limit": "1"},
        )
        if not rows:
            return None
        org_id = int(rows[0]["org_id"])
        org_rows = self._request("GET", _TABLE_ORGS, params={"id": f"eq.{org_id}", "limit": "1"})
        return self._row_org(org_rows[0]) if org_rows else None

    def create_session(self, user_id: int, token: str, expires_at: str) -> None:
        self._request(
            "POST",
            _TABLE_SESSIONS,
            json_body={"token": token, "user_id": user_id, "expires_at": expires_at},
            prefer="return=minimal",
        )

    def create_worker_session(self, org_id: int) -> SessionInfo:
        rows = self._request(
            "GET",
            _TABLE_MEMBERSHIPS,
            params={"org_id": f"eq.{org_id}", "order": "role.desc,user_id.asc", "limit": "1"},
        )
        if not rows:
            raise ValueError("No workspace owner found for queued run")
        user_id = int(rows[0]["user_id"])
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=min(1, PLATFORM_SESSION_DAYS))).isoformat()
        self.create_session(user_id, token, expires)
        return SessionInfo(token=token, user_id=user_id, expires_at=expires)

    def get_session(self, token: str) -> SessionInfo | None:
        rows = self._request("GET", _TABLE_SESSIONS, params={"token": f"eq.{token}", "limit": "1"})
        if not rows:
            return None
        row = rows[0]
        return SessionInfo(token=row["token"], user_id=int(row["user_id"]), expires_at=row["expires_at"])

    def delete_session(self, token: str) -> None:
        self._request("DELETE", _TABLE_SESSIONS, params={"token": f"eq.{token}"}, prefer="return=minimal")

    def delete_sessions_for_user(self, user_id: int) -> None:
        self._request("DELETE", _TABLE_SESSIONS, params={"user_id": f"eq.{user_id}"}, prefer="return=minimal")

    def add_domain(self, org_id: int, domain: str, verify_token: str) -> VerifiedDomain:
        normalized = _normalize_domain(domain)
        existing = self._request(
            "GET",
            _TABLE_DOMAINS,
            params={"org_id": f"eq.{org_id}", "domain": f"eq.{normalized}", "limit": "1"},
        )
        if existing:
            row = existing[0]
            if row.get("status") == "verified":
                return self._row_domain(row)
            rows = self._request(
                "PATCH",
                _TABLE_DOMAINS,
                params={"id": f"eq.{row['id']}"},
                json_body={"status": "pending", "verify_token": verify_token, "verify_method": "dns"},
            )
            return self._row_domain(rows[0])
        rows = self._request(
            "POST",
            _TABLE_DOMAINS,
            json_body={
                "org_id": org_id,
                "domain": normalized,
                "status": "pending",
                "verify_token": verify_token,
                "verify_method": "dns",
            },
        )
        return self._row_domain(rows[0])

    def list_domains(self, org_id: int) -> list[VerifiedDomain]:
        rows = self._request("GET", _TABLE_DOMAINS, params={"org_id": f"eq.{org_id}", "order": "id.asc"})
        return [self._row_domain(row) for row in rows]

    def get_domain(self, domain_id: int, org_id: int) -> VerifiedDomain | None:
        rows = self._request(
            "GET",
            _TABLE_DOMAINS,
            params={"id": f"eq.{domain_id}", "org_id": f"eq.{org_id}", "limit": "1"},
        )
        return self._row_domain(rows[0]) if rows else None

    def mark_domain_verified(self, domain_id: int, *, method: str) -> VerifiedDomain | None:
        verified_at = datetime.now(timezone.utc).isoformat()
        self._request(
            "PATCH",
            _TABLE_DOMAINS,
            params={"id": f"eq.{domain_id}"},
            json_body={"status": "verified", "verify_method": method, "verified_at": verified_at},
            prefer="return=representation",
        )
        rows = self._request("GET", _TABLE_DOMAINS, params={"id": f"eq.{domain_id}", "limit": "1"})
        return self._row_domain(rows[0]) if rows else None

    def add_competitor(self, org_id: int, domain: str) -> OrgCompetitor:
        normalized = _normalize_domain(domain)
        existing = self._request(
            "GET",
            _TABLE_COMPETITORS,
            params={"org_id": f"eq.{org_id}", "domain": f"eq.{normalized}", "limit": "1"},
        )
        if existing:
            return OrgCompetitor(competitor_id=int(existing[0]["id"]), org_id=org_id, domain=normalized)
        rows = self._request(
            "POST",
            _TABLE_COMPETITORS,
            json_body={"org_id": org_id, "domain": normalized},
        )
        row = rows[0] if rows else {"id": 0, "domain": normalized}
        return OrgCompetitor(competitor_id=int(row.get("id", 0)), org_id=org_id, domain=normalized)

    def list_competitors(self, org_id: int) -> list[OrgCompetitor]:
        rows = self._request("GET", _TABLE_COMPETITORS, params={"org_id": f"eq.{org_id}", "order": "domain.asc"})
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
        existing = self._request(
            "GET",
            _TABLE_PROMPTS,
            params={"org_id": f"eq.{org_id}", "external_id": f"eq.{ext}", "limit": "1"},
        )
        if existing:
            rows = self._request(
                "PATCH",
                _TABLE_PROMPTS,
                params={"id": f"eq.{existing[0]['id']}"},
                json_body={
                    "query_text": query_text,
                    "query_class": query_class,
                    "keyword_topic": keyword_topic,
                    "persona": persona,
                    "country": country,
                },
            )
            return self._row_prompt(rows[0])
        rows = self._request(
            "POST",
            _TABLE_PROMPTS,
            json_body={
                "org_id": org_id,
                "external_id": ext,
                "query_text": query_text,
                "query_class": query_class,
                "keyword_topic": keyword_topic,
                "persona": persona,
                "country": country,
            },
        )
        return self._row_prompt(rows[0])

    def list_prompts(self, org_id: int) -> list[OrgPrompt]:
        rows = self._request("GET", _TABLE_PROMPTS, params={"org_id": f"eq.{org_id}", "order": "id.asc"})
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
        artifact_report_uri: str = "",
    ) -> OrgBenchmarkLink:
        rows = self._request(
            "POST",
            _TABLE_BENCHMARKS,
            json_body={
                "org_id": org_id,
                "domain": _normalize_domain(domain),
                "benchmark_run_id": benchmark_run_id,
                "benchmark_score": benchmark_score,
                "band": band,
                "run_at": run_at,
                "artifact_report_uri": artifact_report_uri,
            },
        )
        row = rows[0]
        return OrgBenchmarkLink(
            link_id=int(row["id"]),
            org_id=org_id,
            domain=row["domain"],
            benchmark_run_id=int(row["benchmark_run_id"]),
            benchmark_score=int(row["benchmark_score"]),
            band=row["band"],
            run_at=row["run_at"],
        )

    def list_benchmark_runs(self, org_id: int, limit: int = 12) -> list[OrgBenchmarkLink]:
        rows = self._request(
            "GET",
            _TABLE_BENCHMARKS,
            params={"org_id": f"eq.{org_id}", "order": "run_at.desc", "limit": str(limit)},
        )
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
        rows = self._request(
            "POST",
            _TABLE_RUNS,
            json_body={
                "org_id": org_id,
                "kind": kind,
                "domain": _normalize_domain(domain),
                "status": status,
                "result_summary": result_summary,
            },
        )
        return self._row_run(rows[0])

    def mark_run_running(self, run_id: int, org_id: int) -> PlatformRun | None:
        rows = self._request(
            "PATCH",
            _TABLE_RUNS,
            params={"id": f"eq.{run_id}", "org_id": f"eq.{org_id}", "status": "in.(queued,running)"},
            json_body={"status": "running", "started_at": _now_iso()},
        )
        return self._row_run(rows[0]) if rows else None

    def claim_next_run(self, *, kind: str = "collection", domain: str = "") -> PlatformRun | None:
        params = {
            "kind": f"eq.{kind}",
            "status": "eq.queued",
            "order": "created_at.asc,id.asc",
            "limit": "1",
        }
        if domain:
            params["domain"] = f"eq.{_normalize_domain(domain)}"
        rows = self._request("GET", _TABLE_RUNS, params=params)
        if not rows:
            return None
        run = self._row_run(rows[0])
        claimed = self._request(
            "PATCH",
            _TABLE_RUNS,
            params={"id": f"eq.{run.run_id}", "status": "eq.queued"},
            json_body={"status": "running", "started_at": _now_iso()},
        )
        return self._row_run(claimed[0]) if claimed else None

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
        rows = self._request(
            "PATCH",
            _TABLE_RUNS,
            params={"id": f"eq.{run_id}", "org_id": f"eq.{org_id}"},
            json_body={
                "status": "completed",
                "score": score,
                "band": band,
                "external_run_id": external_run_id,
                "error": "",
                "result_summary": result_summary,
                "completed_at": _now_iso(),
            },
        )
        return self._row_run(rows[0]) if rows else None

    def fail_run(self, run_id: int, org_id: int, *, error: str) -> PlatformRun | None:
        rows = self._request(
            "PATCH",
            _TABLE_RUNS,
            params={"id": f"eq.{run_id}", "org_id": f"eq.{org_id}"},
            json_body={
                "status": "failed",
                "error": error[:1000],
                "completed_at": _now_iso(),
            },
        )
        return self._row_run(rows[0]) if rows else None

    def list_runs(self, org_id: int, *, limit: int = 12, kind: str = "") -> list[PlatformRun]:
        params = {"org_id": f"eq.{org_id}", "order": "created_at.desc,id.desc", "limit": str(limit)}
        if kind:
            params["kind"] = f"eq.{kind}"
        rows = self._request("GET", _TABLE_RUNS, params=params)
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
        self._request(
            "DELETE",
            _TABLE_PAGE_AUDITS,
            params={"org_id": f"eq.{org_id}", "run_id": f"eq.{run_id}"},
            prefer="return=minimal",
        )
        normalized = _normalize_domain(domain)
        body = [
            {
                "org_id": org_id,
                "run_id": run_id,
                "domain": normalized,
                "page_url": str(page.get("page_url") or page.get("url") or "")[:1000],
                "sitemap_url": sitemap_url[:1000],
                "score": int(cast(_IntInput, page.get("score") or 0)),
                "band": str(page.get("band") or "")[:64],
                "http_status": _int_or_none(page.get("http_status")),
                "error": str(page.get("error") or "")[:1000],
                "score_breakdown_json": page.get("score_breakdown") or {},
                "title_issues_json": page.get("title_issues") or [],
                "meta_issues_json": page.get("meta_issues") or [],
                "schema_issues_json": page.get("schema_issues") or [],
                "recommendations_json": page.get("recommendations") or [],
            }
            for page in pages
        ]
        if not body:
            return []
        rows = self._request("POST", _TABLE_PAGE_AUDITS, json_body=body)
        return [self._with_page_history(self._row_page_audit(row)) for row in rows]

    def list_page_audits(
        self,
        org_id: int,
        *,
        domain: str = "",
        run_id: int | None = None,
        limit: int = 100,
    ) -> list[PageAuditRecord]:
        params: dict[str, str] = {
            "org_id": f"eq.{org_id}",
            "order": "created_at.desc,id.desc",
            "limit": str(limit if run_id is not None else max(limit * 5, limit)),
        }
        if domain:
            params["domain"] = f"eq.{_normalize_domain(domain)}"
        if run_id is not None:
            params["run_id"] = f"eq.{run_id}"
        rows = self._request("GET", _TABLE_PAGE_AUDITS, params=params)
        records = [self._row_page_audit(row) for row in rows]
        if run_id is None:
            latest_by_url: dict[str, PageAuditRecord] = {}
            for record in records:
                if record.page_url not in latest_by_url:
                    latest_by_url[record.page_url] = record
            records = list(latest_by_url.values())[:limit]
        return [self._with_page_history(record) for record in records]

    def page_audit_history(self, org_id: int, *, page_url: str, limit: int = 12) -> list[PageAuditRecord]:
        rows = self._request(
            "GET",
            _TABLE_PAGE_AUDITS,
            params={
                "org_id": f"eq.{org_id}",
                "page_url": f"eq.{page_url}",
                "order": "created_at.desc,id.desc",
                "limit": str(limit),
            },
        )
        return [self._with_page_history(self._row_page_audit(row)) for row in rows]

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
        generated = generated_at or _now_iso()
        rows = self._request(
            "POST",
            _TABLE_WEEKLY_EVIDENCE,
            json_body={
                "org_id": org_id,
                "domain": _normalize_domain(domain),
                "period_start": period_start,
                "period_end": period_end,
                "status": status,
                "score": score,
                "band": band,
                "metrics_json": [self._metric_to_dict(metric) for metric in (metrics or [])],
                "action_plan_json": action_plan or {},
                "artifact_json_uri": artifact_json_uri,
                "artifact_html_uri": artifact_html_uri,
                "summary": summary[:2000],
                "generated_at": generated,
            },
        )
        return self._row_weekly_evidence_run(rows[0])

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
        rows = self._request(
            "PATCH",
            _TABLE_WEEKLY_EVIDENCE,
            params={"id": f"eq.{report_id}", "org_id": f"eq.{org_id}"},
            json_body={
                "status": status,
                "score": score,
                "band": band,
                "metrics_json": [self._metric_to_dict(metric) for metric in (metrics or [])],
                "action_plan_json": action_plan or {},
                "artifact_json_uri": artifact_json_uri,
                "artifact_html_uri": artifact_html_uri,
                "summary": summary[:2000],
            },
        )
        return self._row_weekly_evidence_run(rows[0]) if rows else None

    def list_weekly_evidence_runs(
        self,
        org_id: int,
        *,
        domain: str = "",
        limit: int = 12,
    ) -> list[WeeklyEvidenceRun]:
        params = {"org_id": f"eq.{org_id}", "order": "generated_at.desc,id.desc", "limit": str(limit)}
        if domain:
            params["domain"] = f"eq.{_normalize_domain(domain)}"
        rows = self._request("GET", _TABLE_WEEKLY_EVIDENCE, params=params)
        return [self._row_weekly_evidence_run(row) for row in rows]

    def get_latest_weekly_evidence_run(self, org_id: int, *, domain: str = "") -> WeeklyEvidenceRun | None:
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
        created_at = _now_iso()
        rows = self._request(
            "POST",
            _TABLE_AGENT_USAGE,
            json_body={
                "org_id": org_id,
                "domain": _normalize_domain(domain),
                "page_url": page_url[:1000],
                "source_type": source_type[:64],
                "agent": agent[:120],
                "query_text": query[:1000],
                "answer_excerpt": answer_excerpt[:4000],
                "cited_url": cited_url[:1000],
                "cited_rank": cited_rank,
                "surfaced": surfaced,
                "cited": cited,
                "top_recommendation": top_recommendation,
                "confidence": confidence,
                "value_units": value_units,
                "evidence_artifact_id": evidence_artifact_id[:160],
                "evidence_json": json.dumps(evidence or {}, ensure_ascii=False, default=str)[:4000],
                "created_at": created_at,
            },
        )
        return self._row_agent_usage_event(rows[0])

    def list_agent_usage_events(
        self,
        org_id: int,
        *,
        domain: str = "",
        limit: int = 50,
    ) -> list[AgentUsageEvent]:
        params: dict[str, str] = {
            "org_id": f"eq.{org_id}",
            "order": "created_at.desc,id.desc",
            "limit": str(limit),
        }
        if domain:
            params["domain"] = f"eq.{_normalize_domain(domain)}"
        rows = self._request("GET", _TABLE_AGENT_USAGE, params=params)
        return [self._row_agent_usage_event(row) for row in rows]

    def index_summary(self, org_id: int, *, domain: str = "") -> IndexTelemetrySummary:
        normalized = _normalize_domain(domain) if domain else ""
        events = self.list_agent_usage_events(org_id, domain=normalized, limit=1000)
        if not events:
            return IndexTelemetrySummary(domain=normalized, action_plan=self._index_action_plan([]))
        citation_events = [event for event in events if self._is_answer_visibility_source(event)]
        denominator = len(citation_events) or len(events)
        surfaced = sum(1 for event in events if event.surfaced)
        cited = sum(1 for event in citation_events if event.cited)
        top = sum(1 for event in citation_events if event.top_recommendation)
        return IndexTelemetrySummary(
            domain=normalized or events[0].domain,
            total_events=len(events),
            surfaced_events=surfaced,
            cited_events=cited,
            top_recommendation_events=top,
            citation_rate=round(cited / denominator, 4),
            top_recommendation_rate=round(top / denominator, 4),
            total_value_units=round(sum(event.value_units for event in events), 2),
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
        normalized = _normalize_domain(domain)
        variants = {normalized}
        if normalized.startswith("www."):
            variants.add(normalized[4:])
        else:
            variants.add(f"www.{normalized}")
        rows = self._request(
            "GET",
            _TABLE_DOMAINS,
            params={"domain": f"in.({','.join(sorted(variants))})", "select": "status"},
        )
        statuses = [str(row.get("status", "")) for row in rows]
        return {
            "domain": normalized,
            "claimed": bool(statuses),
            "verified": any(status == "verified" for status in statuses),
        }

    def _row_user(self, row: dict) -> PlatformUser:
        return PlatformUser(
            user_id=int(row["id"]),
            email=row["email"],
            email_domain=row["email_domain"],
            created_at=str(row.get("created_at", "")),
        )

    def _row_org(self, row: dict) -> Organization:
        return Organization(
            org_id=int(row["id"]),
            name=row["name"],
            email_domain=row["email_domain"],
            slug=row["slug"],
            created_at=str(row.get("created_at", "")),
        )

    def _row_domain(self, row: dict) -> VerifiedDomain:
        return VerifiedDomain(
            domain_id=int(row["id"]),
            org_id=int(row["org_id"]),
            domain=row["domain"],
            status=row["status"],
            verify_token=row["verify_token"],
            verify_method=row.get("verify_method") or "",
            verified_at=row.get("verified_at"),
            created_at=str(row.get("created_at", "")),
        )

    def _row_prompt(self, row: dict) -> OrgPrompt:
        return OrgPrompt(
            prompt_id=int(row["id"]),
            org_id=int(row["org_id"]),
            external_id=row.get("external_id", ""),
            query_text=row["query_text"],
            query_class=row.get("query_class", ""),
            keyword_topic=row.get("keyword_topic", ""),
            persona=row.get("persona", ""),
            country=row.get("country", ""),
        )

    def _row_run(self, row: dict) -> PlatformRun:
        return PlatformRun(
            run_id=int(row["id"]),
            org_id=int(row["org_id"]),
            kind=row["kind"],
            domain=row["domain"],
            status=row["status"],
            score=int(row["score"]) if row.get("score") is not None else None,
            band=row.get("band") or "",
            external_run_id=row.get("external_run_id") or "",
            error=row.get("error") or "",
            result_summary=row.get("result_summary") or "",
            created_at=str(row.get("created_at", "")),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )

    def _row_page_audit(self, row: dict) -> PageAuditRecord:
        return PageAuditRecord(
            page_audit_id=int(row["id"]),
            org_id=int(row["org_id"]),
            run_id=int(row["run_id"]),
            domain=row["domain"],
            page_url=row["page_url"],
            sitemap_url=row.get("sitemap_url") or "",
            score=int(row.get("score") or 0),
            band=row.get("band") or "",
            http_status=int(row["http_status"]) if row.get("http_status") is not None else None,
            error=row.get("error") or "",
            score_breakdown=self._json_dict(row.get("score_breakdown_json")),
            title_issues=self._json_list(row.get("title_issues_json")),
            meta_issues=self._json_list(row.get("meta_issues_json")),
            schema_issues=self._json_list(row.get("schema_issues_json")),
            recommendations=self._json_list(row.get("recommendations_json")),
            created_at=str(row.get("created_at", "")),
        )

    def _with_page_history(self, record: PageAuditRecord) -> PageAuditRecord:
        rows = self._request(
            "GET",
            _TABLE_PAGE_AUDITS,
            params={
                "org_id": f"eq.{record.org_id}",
                "page_url": f"eq.{record.page_url}",
                "id": f"lt.{record.page_audit_id}",
                "select": "score",
                "order": "id.desc",
                "limit": "1",
            },
        )
        if not rows:
            return record
        previous = int(rows[0].get("score") or 0)
        record.previous_score = previous
        record.score_delta = record.score - previous
        return record

    def _row_weekly_evidence_run(self, row: dict) -> WeeklyEvidenceRun:
        metrics_raw = row.get("metrics_json") or []
        if isinstance(metrics_raw, str):
            try:
                metrics_raw = json.loads(metrics_raw)
            except ValueError:
                metrics_raw = []
        action_plan = row.get("action_plan_json") or {}
        if isinstance(action_plan, str):
            try:
                action_plan = json.loads(action_plan)
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
            status=row.get("status", "completed"),
            generated_at=row.get("generated_at", ""),
            score=int(row["score"]) if row.get("score") is not None else None,
            band=row.get("band", ""),
            metrics=metrics,
            artifact_json_uri=row.get("artifact_json_uri", ""),
            artifact_html_uri=row.get("artifact_html_uri", ""),
            summary=row.get("summary", ""),
            action_plan=action_plan if isinstance(action_plan, dict) else {},
        )

    def _row_agent_usage_event(self, row: dict) -> AgentUsageEvent:
        evidence: dict[str, object] = {}
        try:
            parsed = json.loads(str(row.get("evidence_json") or "{}"))
            if isinstance(parsed, dict):
                evidence = parsed
        except json.JSONDecodeError:
            evidence = {}
        return AgentUsageEvent(
            event_id=int(row["id"]),
            org_id=int(row["org_id"]),
            domain=row["domain"],
            page_url=row.get("page_url") or "",
            source_type=row["source_type"],
            agent=row.get("agent") or "",
            query=row.get("query_text") or "",
            answer_excerpt=row.get("answer_excerpt") or "",
            cited_url=row.get("cited_url") or "",
            cited_rank=int(row["cited_rank"]) if row.get("cited_rank") is not None else None,
            surfaced=bool(row.get("surfaced")),
            cited=bool(row.get("cited")),
            top_recommendation=bool(row.get("top_recommendation")),
            confidence=float(row.get("confidence", 1.0)),
            value_units=float(row.get("value_units", 0.0)),
            evidence_artifact_id=str(row.get("evidence_artifact_id") or ""),
            evidence=evidence,
            created_at=str(row.get("created_at", "")),
        )

    @staticmethod
    def _json_dict(raw: object) -> dict[str, object]:
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw or "{}"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_list(raw: object) -> list[str]:
        if isinstance(raw, list):
            return [str(item) for item in raw]
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
        return SupabasePlatformStore._count_by(missed, "query", limit=limit)

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
        return event.source_type not in {"crawler_log", "retrieval_probe", "serp_check"}

    @staticmethod
    def _has_source(events: list[AgentUsageEvent], source_type: str) -> bool:
        return any(event.source_type == source_type for event in events)

    @staticmethod
    def _index_action_plan(events: list[AgentUsageEvent]) -> dict[str, object]:
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
        answer_events = [event for event in events if SupabasePlatformStore._is_answer_visibility_source(event)]
        if not answer_events:
            if SupabasePlatformStore._has_source(events, "serp_check"):
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

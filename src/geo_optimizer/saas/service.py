"""Platform business logic: workspace, verify, audit, benchmark."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import smtplib
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import SupportsFloat, SupportsIndex, TypedDict, Union, cast
from urllib.parse import urlparse

import requests

from geo_optimizer.core.audit import run_full_audit
from geo_optimizer.core.audit_serp import audit_serp
from geo_optimizer.core.batch_audit import run_batch_audit
from geo_optimizer.core.benchmark.runner import run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.collection.normalize import batch_from_dict, batch_to_benchmark_answers
from geo_optimizer.core.llms_generator import discover_sitemap
from geo_optimizer.core.monitor import normalize_monitor_domain
from geo_optimizer.core.snapshots import extract_citations
from geo_optimizer.saas.auth import login_user, register_user, request_password_reset, reset_password, resolve_session
from geo_optimizer.saas.domain_verify import (
    dns_verify_hostname,
    generate_verify_token,
    https_verify_url,
    verify_domain,
)
from geo_optimizer.saas.models import AgencyLoopState, AgencyLoopStep, IndexTelemetrySummary, PlatformDashboard
from geo_optimizer.saas.store import _IntInput
from geo_optimizer.saas.weekly_evidence import build_weekly_evidence_report, metric_objects
from geo_optimizer.utils.validators import url_belongs_to_domain

_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_FloatInput = Union[str, bytes, bytearray, SupportsFloat, SupportsIndex]


class _ProviderReadiness(TypedDict):
    available_providers: list[str]
    missing: list[str]
    ready: bool


def _score_value(value: object) -> float:
    try:
        return float(cast(_FloatInput, value or 0))
    except (TypeError, ValueError):
        return 0.0


class PlatformService:
    """Orchestrates tenant operations on top of PlatformStore."""

    def __init__(self, store=None):
        if store is None:
            from geo_optimizer.storage.platform import get_platform_store

            store = get_platform_store()
        self.store = store

    def register(self, *, email: str, password: str, org_name: str = "") -> dict:
        user, org, session = register_user(self.store, email=email, password=password, org_name=org_name)
        return {
            "user": asdict(user),
            "organization": asdict(org),
            "session": {"token": session.token, "expires_at": session.expires_at},
        }

    def login(self, *, email: str, password: str) -> dict:
        user, org, session = login_user(self.store, email=email, password=password)
        return {
            "user": asdict(user),
            "organization": asdict(org),
            "session": {"token": session.token, "expires_at": session.expires_at},
        }

    def request_password_reset(self, *, email: str, base_url: str = "") -> dict:
        payload = request_password_reset(self.store, email=email)
        token = str(payload.pop("reset_token", "") or "")
        reset_base_url = self._password_reset_base_url(base_url)
        reset_url = f"{reset_base_url}/platform/reset-password?token={token}" if token and reset_base_url else ""
        plunk_enabled = self._plunk_enabled()
        webhook_enabled = self._webhook_enabled()
        smtp_enabled = self._smtp_enabled()
        development_links_enabled = self._development_reset_links_enabled(base_url)
        if reset_url and plunk_enabled:
            self._send_password_reset_plunk(email=email.strip().lower(), reset_url=reset_url)
            payload["delivery"] = "plunk"
        elif reset_url and webhook_enabled:
            self._send_password_reset_webhook(email=email.strip().lower(), reset_url=reset_url)
            payload["delivery"] = "webhook"
        elif reset_url and smtp_enabled:
            self._send_password_reset_email(email=email.strip().lower(), reset_url=reset_url)
            payload["delivery"] = "email"
        elif reset_url and development_links_enabled:
            payload["reset_url"] = reset_url
            payload["delivery"] = "development_link"
        elif reset_url:
            payload["delivery"] = "email_unconfigured"
            payload["message"] = "Password reset email is not configured yet. Contact support."
        elif token and (plunk_enabled or webhook_enabled or smtp_enabled):
            payload["delivery"] = "email_unconfigured"
            payload["message"] = "Password reset public URL is not configured. Contact support."
        elif token:
            payload["delivery"] = "email_unconfigured"
            payload["message"] = "Password reset email is not configured yet. Contact support."
        else:
            payload["delivery"] = (
                "plunk"
                if plunk_enabled
                else "webhook"
                if webhook_enabled
                else "email"
                if smtp_enabled
                else ("development_link" if development_links_enabled else "email_unconfigured")
            )
        return payload

    def reset_password(self, *, token: str, password: str) -> dict:
        reset_password(self.store, token=token, password=password)
        return {"ok": True, "message": "Password updated. You can sign in with your new password."}

    @staticmethod
    def _smtp_enabled() -> bool:
        return bool(os.environ.get("GEOSITION_SMTP_HOST", "").strip())

    @staticmethod
    def _webhook_enabled() -> bool:
        return bool(os.environ.get("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", "").strip())

    @staticmethod
    def _plunk_enabled() -> bool:
        return bool(
            os.environ.get("GEOSITION_PLUNK_API_KEY", "").strip() or os.environ.get("PLUNK_API_KEY", "").strip()
        )

    @staticmethod
    def _development_reset_links_enabled(base_url: str) -> bool:
        """Only expose reset URLs directly in local/test development."""
        if os.environ.get("VERCEL", "").strip().lower() in {"1", "true", "yes", "on"}:
            return False
        mode = os.environ.get("GEOSITION_PASSWORD_RESET_MODE", "").strip().lower()
        if mode in {"development_link", "development", "dev", "local"}:
            return True
        host = (urlparse(base_url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1", "testserver"} or host.endswith(".local")

    @staticmethod
    def _password_reset_base_url(base_url: str) -> str:
        configured = os.environ.get("GEOSITION_PUBLIC_BASE_URL", "").strip().rstrip("/")
        if configured:
            parsed = urlparse(configured)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise RuntimeError("GEOSITION_PUBLIC_BASE_URL must be an absolute http(s) URL")
            return configured
        if PlatformService._development_reset_links_enabled(base_url):
            return base_url.rstrip("/")
        return ""

    @staticmethod
    def _send_password_reset_email(*, email: str, reset_url: str) -> None:
        host = os.environ.get("GEOSITION_SMTP_HOST", "").strip()
        port = int(os.environ.get("GEOSITION_SMTP_PORT", "587"))
        username = os.environ.get("GEOSITION_SMTP_USERNAME", "").strip()
        password = os.environ.get("GEOSITION_SMTP_PASSWORD", "")
        sender = os.environ.get("GEOSITION_SMTP_FROM", "").strip() or username or "no-reply@geosition.local"
        use_ssl = os.environ.get("GEOSITION_SMTP_SSL", "").strip().lower() in {"1", "true", "yes", "on"}
        use_tls = os.environ.get("GEOSITION_SMTP_TLS", "1").strip().lower() not in {"0", "false", "no", "off"}

        message = EmailMessage()
        message["Subject"] = "Reset your GEOSITION password"
        message["From"] = sender
        message["To"] = email
        message.set_content(
            "Use this one-time link to reset your GEOSITION password:\n\n"
            f"{reset_url}\n\n"
            "The link expires in 60 minutes. If you did not request this, you can ignore this email.\n"
        )

        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                if username or password:
                    smtp.login(username, password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if username or password:
                smtp.login(username, password)
            smtp.send_message(message)

    @staticmethod
    def _password_reset_message(reset_url: str) -> tuple[str, str, str]:
        subject = "Reset your GEOSITION password"
        text = (
            "Use this one-time link to reset your GEOSITION password:\n\n"
            f"{reset_url}\n\n"
            "The link expires in 60 minutes. If you did not request this, you can ignore this email.\n"
        )
        escaped_reset_url = escape(reset_url, quote=True)
        html = (
            "<p>Use this one-time link to reset your GEOSITION password:</p>"
            f'<p><a href="{escaped_reset_url}">Choose a new password</a></p>'
            "<p>The link expires in 60 minutes. If you did not request this, you can ignore this email.</p>"
        )
        return subject, text, html

    @staticmethod
    def _send_password_reset_plunk(*, email: str, reset_url: str) -> None:
        api_key = os.environ.get("GEOSITION_PLUNK_API_KEY", os.environ.get("PLUNK_API_KEY", "")).strip()
        url = os.environ.get("GEOSITION_PLUNK_API_URL", "https://next-api.useplunk.com/v1/send").strip()
        sender = os.environ.get("GEOSITION_PASSWORD_RESET_FROM", "").strip() or "no-reply@geosition.local"
        subject, _text, html = PlatformService._password_reset_message(reset_url)
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "to": email,
                "from": sender,
                "subject": subject,
                "body": html,
                "subscribed": False,
                "data": {
                    "reset_url": {"value": reset_url, "persistent": False},
                },
            },
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Plunk password reset email failed: {response.status_code} {response.text[:200]}")

    @staticmethod
    def _send_password_reset_webhook(*, email: str, reset_url: str) -> None:
        url = os.environ.get("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", "").strip()
        secret = os.environ.get("GEOSITION_PASSWORD_RESET_WEBHOOK_SECRET", "").strip()
        sender = os.environ.get("GEOSITION_PASSWORD_RESET_FROM", "").strip() or "no-reply@geosition.local"
        subject, text, html = PlatformService._password_reset_message(reset_url)
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        response = requests.post(
            url,
            headers=headers,
            json={
                "to": email,
                "from": sender,
                "subject": subject,
                "text": text,
                "html": html,
                "reset_url": reset_url,
            },
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Password reset webhook failed: {response.status_code} {response.text[:200]}")

    def logout(self, token: str) -> None:
        self.store.delete_session(token)

    def require_session(self, token: str) -> tuple:
        resolved = resolve_session(self.store, token)
        if resolved is None:
            raise PermissionError("Invalid or expired session")
        return resolved

    def storage_health(self, token: str) -> dict[str, object]:
        """Return platform storage readiness for the authenticated workspace."""
        self.require_session(token)
        return self._storage_health()

    def _storage_health(self) -> dict[str, object]:
        """Return platform storage readiness without requiring a user session."""
        checker = getattr(self.store, "storage_health", None)
        if checker is None:
            return {
                "backend": type(self.store).__name__,
                "ok": False,
                "required_migrations": [],
                "missing_migrations": [],
                "tables": [],
                "error": "Platform store does not expose storage health checks.",
            }
        return cast(dict[str, object], checker())

    def production_health_check(self) -> dict[str, object]:
        """Return deploy-time platform readiness for protected smoke checks."""
        storage = self._storage_health()
        providers = self._collection_provider_readiness()
        reset_delivery = self._password_reset_delivery_health()
        worker = {
            "configured": bool(os.environ.get("GEOSITION_WORKER_TOKEN", "").strip()),
            "env": "GEOSITION_WORKER_TOKEN",
        }
        supabase = {
            "backend": storage.get("backend", type(self.store).__name__),
            "url_configured": bool(
                os.environ.get("SUPABASE_URL", os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")).strip()
            ),
            "service_role_configured": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()),
            "forced_backend": os.environ.get("GEO_PLATFORM_BACKEND", "").strip() or "auto",
        }
        critical_ok = bool(storage.get("ok")) and bool(reset_delivery["ready"]) and bool(worker["configured"])
        return {
            "ok": critical_ok,
            "checks": {
                "storage": storage,
                "supabase": supabase,
                "password_reset": reset_delivery,
                "worker": worker,
                "providers": providers,
            },
            "next_actions": self._production_health_next_actions(
                storage=storage,
                reset_delivery=reset_delivery,
                worker=worker,
                providers=providers,
                supabase=supabase,
            ),
        }

    @staticmethod
    def _password_reset_delivery_health() -> dict[str, object]:
        plunk = PlatformService._plunk_enabled()
        webhook = PlatformService._webhook_enabled()
        smtp = PlatformService._smtp_enabled()
        public_base_url = os.environ.get("GEOSITION_PUBLIC_BASE_URL", "").strip()
        configured_modes = []
        if plunk:
            configured_modes.append("plunk")
        if webhook:
            configured_modes.append("webhook")
        if smtp:
            configured_modes.append("smtp")
        return {
            "ready": bool(configured_modes and public_base_url),
            "configured_modes": configured_modes,
            "public_base_url_configured": bool(public_base_url),
            "development_link_enabled": os.environ.get("GEOSITION_PASSWORD_RESET_MODE", "").strip().lower()
            in {"development_link", "development", "dev", "local"},
            "required_for_production": [
                "GEOSITION_PUBLIC_BASE_URL",
                "GEOSITION_PLUNK_API_KEY or GEOSITION_PASSWORD_RESET_WEBHOOK_URL or GEOSITION_SMTP_HOST",
            ],
        }

    @staticmethod
    def _production_health_next_actions(
        *,
        storage: dict[str, object],
        reset_delivery: dict[str, object],
        worker: dict[str, object],
        providers: Mapping[str, object],
        supabase: dict[str, object],
    ) -> list[str]:
        actions = []
        if not storage.get("ok"):
            migrations = (
                ", ".join(str(item) for item in cast(list[str], storage.get("missing_migrations", [])))
                or "platform migrations"
            )
            actions.append(f"Apply missing Supabase/platform storage migrations: {migrations}.")
        if supabase.get("forced_backend") == "supabase" and not supabase.get("service_role_configured"):
            actions.append("Set SUPABASE_SERVICE_ROLE_KEY for durable platform writes.")
        if not reset_delivery.get("ready"):
            actions.append("Configure GEOSITION_PUBLIC_BASE_URL plus Plunk, webhook, or SMTP password reset delivery.")
        if not worker.get("configured"):
            actions.append("Set GEOSITION_WORKER_TOKEN so hosted page audits and collection workers can run.")
        if not providers.get("ready"):
            missing = (
                ", ".join(str(item) for item in cast(list[str], providers.get("missing", []))) or "provider credentials"
            )
            actions.append(f"Set hosted collection provider credentials: {missing}.")
        return actions

    def dashboard(self, token: str) -> PlatformDashboard:
        user, org = self.require_session(token)
        domains = self.store.list_domains(org.org_id)
        verified = [d for d in domains if d.status == "verified"]
        primary_verified = verified[0].domain if verified else ""
        target_domain = primary_verified or (domains[0].domain if domains else "")
        recent_benchmarks = self.store.list_benchmark_runs(org.org_id)
        recent_page_audits = self._dashboard_page_audits(org.org_id, domain=target_domain)
        recent_weekly_reports = self._dashboard_weekly_reports(org.org_id, domain=target_domain)
        index_summary = self._dashboard_index_summary(org.org_id, domain=target_domain)
        return PlatformDashboard(
            organization=org,
            user=user,
            domains=domains,
            competitors=self.store.list_competitors(org.org_id),
            prompts=self.store.list_prompts(org.org_id),
            recent_benchmarks=recent_benchmarks,
            recent_runs=self.store.list_runs(org.org_id),
            recent_page_audits=recent_page_audits,
            recent_weekly_reports=recent_weekly_reports,
            index_summary=index_summary,
            agency_loop=self._agency_loop_state(
                target_domain=target_domain,
                has_verified=bool(primary_verified),
                page_audits=recent_page_audits,
                benchmarks=recent_benchmarks,
                weekly_reports=recent_weekly_reports,
                index_summary=index_summary,
            ),
            primary_verified_domain=primary_verified,
            target_domain=target_domain,
        )

    def _agency_loop_state(
        self,
        *,
        target_domain: str,
        has_verified: bool,
        page_audits: list,
        benchmarks: list,
        weekly_reports: list,
        index_summary: IndexTelemetrySummary,
    ) -> AgencyLoopState:
        """Derive the client operating loop from saved evidence, not front-end guesses."""
        domain_label = target_domain or "this client domain"
        has_pages = bool(page_audits)
        has_benchmark = any(not target_domain or item.domain == target_domain for item in benchmarks)
        has_report = bool(weekly_reports)
        has_index_evidence = index_summary.total_events > 0

        if not has_verified:
            current_step = "verify"
            next_action = "Verify domain"
            next_target = "verify"
            summary = (
                "Add DNS TXT or HTTPS file verification to unlock audits, benchmarks, reports, and value tracking."
            )
            proof_focus = "Ownership proof is the gate before GEOSITION can store client evidence."
        elif not has_pages:
            current_step = "pages"
            next_action = "Run page audit"
            next_target = "pages"
            summary = f"{domain_label} is verified. Start by auditing sitemap URLs and page-level GEO/SEO/CRO issues."
            proof_focus = (
                "Creates the baseline by URL: score, title/meta/schema issues, crawler access, and recommendations."
            )
        elif not has_benchmark:
            current_step = "benchmark"
            next_action = "Run benchmark"
            next_target = "benchmark"
            summary = f"{domain_label} has page evidence. Benchmark prompts next so client visibility has a baseline."
            proof_focus = "Creates the baseline by prompt: cited, surfaced, missed, and competitor comparison evidence."
        elif not has_report:
            current_step = "skill"
            next_action = "Copy Skill Files"
            next_target = "skill"
            summary = (
                "Page and prompt baselines exist. Hand the right GEOSITION context to the AI tool that will make fixes."
            )
            proof_focus = "Skill Files connect audit findings to concrete code/content fixes, then the same URLs and prompts can be re-run."
        elif not has_index_evidence:
            current_step = "report"
            next_action = "Record AI visibility evidence"
            next_target = "report"
            summary = (
                "Weekly proof exists. Add Index evidence or hosted collection so reports include citation movement."
            )
            proof_focus = (
                "Completes the agency proof loop with citation/share movement, not only technical audit scores."
            )
        else:
            current_step = "report"
            next_action = "Re-run weekly proof"
            next_target = "report"
            summary = "The agency loop is active. Keep the same URLs and prompts on a weekly cadence to prove movement."
            proof_focus = (
                "Shows before/after deltas by URL, prompt, crawler access, citation share, and benchmark score."
            )

        raw_steps = [
            (
                "verify",
                "01",
                "Verify domain",
                "Add DNS TXT or HTTPS file ownership. This ties every run and report to the client.",
                "Verify domain",
                "DNS or HTTPS ownership proof",
                "free",
            ),
            (
                "pages",
                "02",
                "Run page audit",
                "Audit sitemap URLs for title, meta, schema, crawler access, content, and score issues.",
                "Run page audit",
                "Before baseline by URL",
                "free",
            ),
            (
                "benchmark",
                "03",
                "Run benchmark",
                "Test target prompts against competitors and record where AI answers cite or miss the client.",
                "Run benchmark",
                "Before baseline by prompt",
                "free",
            ),
            (
                "skill",
                "04",
                "Copy Skill Files",
                "Give Cursor, Claude, Codex, or the CLI the GEOSITION workflow and file context before fixing.",
                "Copy Skill Files",
                "Fix handoff context",
                "free",
            ),
            (
                "fix",
                "05",
                "Fix pages",
                "Apply the highest-impact recommendations to the URLs and prompts with visible gaps.",
                "Fix client pages",
                "Implementation notes",
                "free",
            ),
            (
                "report",
                "06",
                "Re-run proof",
                "Re-run audits, benchmarks, and weekly evidence so clients see before/after movement.",
                "Weekly proof",
                "Before/after deltas",
                "paid",
            ),
        ]
        order = [item[0] for item in raw_steps]
        current_index = order.index(current_step)
        steps = []
        for index, (step_id, number, title, description, action, proof, plan) in enumerate(raw_steps):
            if index < current_index or (step_id == "verify" and has_verified):
                state = "done"
                label = "Done"
            elif step_id == current_step:
                state = "current"
                label = "Now"
            else:
                state = "waiting"
                label = "Waiting"
            steps.append(
                AgencyLoopStep(
                    step_id=step_id,
                    number=number,
                    title=title,
                    description=description,
                    state=state,
                    label=label,
                    action=action,
                    proof=proof,
                    plan=plan,
                )
            )

        return AgencyLoopState(
            current_step=current_step,
            next_action=next_action,
            next_action_target=next_target,
            summary=summary,
            proof_focus=proof_focus,
            steps=steps,
        )

    def _dashboard_page_audits(self, org_id: int, *, domain: str) -> list:
        """Best-effort optional page rows for dashboard rendering during staged migrations."""
        if not domain:
            return []
        try:
            return cast(list, self.store.list_page_audits(org_id, domain=domain, limit=50))
        except RuntimeError:
            return []

    def _dashboard_weekly_reports(self, org_id: int, *, domain: str) -> list:
        """Best-effort optional weekly rows for dashboard rendering during staged migrations."""
        if not domain:
            return []
        try:
            return cast(list, self.store.list_weekly_evidence_runs(org_id, domain=domain))
        except RuntimeError:
            return []

    def _dashboard_index_summary(self, org_id: int, *, domain: str) -> IndexTelemetrySummary:
        """Best-effort Index metrics for dashboard rendering during staged migrations."""
        try:
            return cast(IndexTelemetrySummary, self.store.index_summary(org_id, domain=domain))
        except RuntimeError:
            return IndexTelemetrySummary(domain=domain)

    def list_weekly_reports(self, token: str, *, domain: str = "", limit: int = 12) -> list[dict]:
        """List durable weekly evidence reports for a verified domain."""
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing weekly reports.")
        self._require_verified(org.org_id, normalized)
        return [
            asdict(report)
            for report in self.store.list_weekly_evidence_runs(org.org_id, domain=normalized, limit=limit)
        ]

    def latest_weekly_report(self, token: str, *, domain: str = "") -> dict | None:
        """Return the latest weekly evidence report for a verified domain."""
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing weekly reports.")
        self._require_verified(org.org_id, normalized)
        report = self.store.get_latest_weekly_evidence_run(org.org_id, domain=normalized)
        return asdict(report) if report else None

    def run_weekly_evidence_report(
        self,
        token: str,
        *,
        domain: str,
        answers_payload: dict | list | None = None,
        lighthouse_provider: str = "pagespeed",
    ) -> dict:
        """Run and persist a weekly GEO/SEO/CRO evidence report."""
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)
        competitors = [competitor.domain for competitor in self.store.list_competitors(org.org_id)]

        from geo_optimizer.storage.paths import resolve_benchmark_db_path

        bench_db = os.environ.get("GEO_BENCHMARK_DB")
        benchmark_store = BenchmarkStore(Path(bench_db) if bench_db else resolve_benchmark_db_path())
        try:
            report = build_weekly_evidence_report(
                normalized,
                answers_payload=answers_payload,
                competitors=competitors,
                lighthouse_provider=lighthouse_provider,
                benchmark_store=benchmark_store,
            )
            report["collection_mode"] = "live"
        except Exception as exc:
            report = self._fallback_weekly_evidence_report(org.org_id, normalized, error=str(exc))

        self._attach_weekly_delta_evidence(report, org.org_id, normalized)

        try:
            record = self.store.create_weekly_evidence_run(
                org.org_id,
                domain=normalized,
                period_start=str(report["period_start"]),
                period_end=str(report["period_end"]),
                status="completed",
                score=int(report["score"]),
                band=str(report["band"]),
                metrics=metric_objects(list(report.get("metrics", []))),
                summary=str(report["summary"]),
                action_plan=dict(report.get("action_plan", {})),
                generated_at=str(report["generated_at"]),
            )
            report["report"] = asdict(record)
        except RuntimeError as exc:
            report["report"] = {}
            report["persistence_warning"] = (
                "Weekly report was generated but could not be saved. "
                "Apply the Supabase weekly evidence migration and try again."
            )
            report["technical_error"] = str(exc)[:240]
        return report

    def _attach_weekly_delta_evidence(self, report: dict, org_id: int, domain: str) -> None:
        """Attach URL and prompt deltas from stored evidence to a weekly report payload."""
        pages = self._dashboard_page_audits(org_id, domain=domain)
        index = self._dashboard_index_summary(org_id, domain=domain)
        url_deltas: list[dict[str, object]] = []
        for page in pages[:25]:
            url_deltas.append(
                {
                    "url": page.page_url,
                    "before_score": page.previous_score,
                    "after_score": page.score,
                    "delta": page.score_delta,
                    "status": "baseline" if page.score_delta is None else "changed",
                    "recommendations": page.recommendations[:5],
                }
            )
        prompt_deltas: list[dict[str, object]] = []
        for query, count in list(index.top_queries.items())[:25]:
            cited_count = sum(1 for event in index.recent_events if event.query == query and event.cited)
            prompt_deltas.append(
                {
                    "prompt": query,
                    "before_citations": None,
                    "after_citations": count,
                    "delta": None,
                    "status": "baseline",
                    "note": (
                        f"{count} observed answer event(s); {cited_count} top cited page match(es). "
                        "Run the same prompt set again to calculate before/after prompt deltas."
                    ),
                }
            )
        report["deltas"] = {
            "urls": url_deltas,
            "prompts": prompt_deltas,
            "summary": "URL deltas use page audit history; prompt deltas use repeated benchmark or Index evidence.",
        }

    def _fallback_weekly_evidence_report(self, org_id: int, domain: str, *, error: str) -> dict:
        """Build a no-network weekly snapshot from already stored platform evidence."""
        generated = datetime.now(timezone.utc)
        period_start = (generated - timedelta(days=7)).isoformat()
        period_end = generated.isoformat()
        index = self._dashboard_index_summary(org_id, domain=domain)
        pages = self._dashboard_page_audits(org_id, domain=domain)
        latest_score = pages[0].score if pages else None
        score = int(latest_score) if latest_score is not None else 0
        if score <= 0 and index.total_events:
            score = min(100, int(round(index.citation_rate * 70 + index.top_recommendation_rate * 30)))
        band = "excellent" if score >= 86 else "good" if score >= 68 else "foundation" if score >= 36 else "collecting"
        metrics = [
            {
                "key": "stored_page_audits",
                "label": "Stored page audits",
                "value": str(len(pages)),
                "unit": "pages",
                "status": "good" if pages else "watch",
                "evidence_ref": "page_audits",
            },
            {
                "key": "index_events",
                "label": "Index evidence events",
                "value": str(index.total_events),
                "unit": "events",
                "status": "good" if index.total_events else "watch",
                "evidence_ref": "index",
            },
            {
                "key": "citation_rate",
                "label": "Citation rate",
                "value": f"{index.citation_rate:.0%}",
                "unit": "percent",
                "status": "good" if index.citation_rate > 0 else "watch",
                "evidence_ref": "index",
            },
        ]
        if latest_score is not None:
            metrics.insert(
                0,
                {
                    "key": "latest_page_score",
                    "label": "Latest page score",
                    "value": f"{latest_score}/100",
                    "unit": "score",
                    "status": "good" if latest_score >= 68 else "watch",
                    "evidence_ref": "page_audits",
                },
            )
        return {
            "schema_version": "weekly_evidence.v1",
            "domain": domain,
            "url": normalize_monitor_domain(domain),
            "period_start": period_start,
            "period_end": period_end,
            "generated_at": period_end,
            "score": score,
            "band": band,
            "summary": (
                "Generated a stored-evidence weekly snapshot. Live audit collection was unavailable, "
                "so this report uses page-audit and Index evidence already saved for the workspace."
            ),
            "metrics": metrics,
            "sources": {
                "page_audits": {"checked": bool(pages), "count": len(pages)},
                "index": {"checked": True, "events": index.total_events},
                "live_collection": {"checked": False, "reason": error[:240]},
            },
            "action_plan": {
                "actions": [
                    "Run a page audit after the worker or live audit endpoint is available.",
                    "Record AI answer evidence or run benchmark collection to populate citation trends.",
                    "Apply recommendations from the latest page audit rows.",
                ]
            },
            "collection_mode": "stored_evidence_fallback",
            "technical_error": error[:240],
        }

    def add_website_domain(self, token: str, domain: str) -> dict:
        """Register a website domain.

        Account email and website ownership are separate: users may sign up with
        Gmail, Outlook, or another mailbox, then prove site ownership with DNS or
        HTTPS verification.
        """
        _user, org = self.require_session(token)
        normalized = self._normalize_verifiable_domain(domain)
        verify_token = generate_verify_token()
        record = self.store.add_domain(org.org_id, normalized, verify_token)
        return {
            "domain": asdict(record),
            "dns_host": dns_verify_hostname(normalized),
            "dns_value": f"geo-verify={verify_token}",
            "https_url": https_verify_url(normalized),
            "https_body": f"geo-verify={verify_token}",
        }

    def check_domain_verification(self, token: str, domain_id: int, *, method: str = "dns") -> dict:
        user, org = self.require_session(token)
        record = self.store.get_domain(domain_id, org.org_id)
        if record is None:
            raise ValueError("Domain not found")
        ok, message = verify_domain(record.domain, record.verify_token, method=method)
        collection = None
        if ok:
            record = self.store.mark_domain_verified(record.domain_id, method=method)
            if record is not None and self._auto_collection_enabled():
                collection = self.queue_hosted_collection(token, domain=record.domain)
        return {
            "verified": ok,
            "message": message,
            "domain": asdict(record) if record else {},
            "collection": collection,
        }

    def add_competitor(self, token: str, domain: str) -> dict:
        user, org = self.require_session(token)
        self._require_any_verified_domain(org.org_id)
        comp = self.store.add_competitor(org.org_id, domain)
        return asdict(comp)

    def add_prompt(
        self,
        token: str,
        *,
        query_text: str,
        external_id: str = "",
        query_class: str = "",
        keyword_topic: str = "",
    ) -> dict:
        user, org = self.require_session(token)
        self._require_any_verified_domain(org.org_id)
        prompt = self.store.add_prompt(
            org.org_id,
            external_id=external_id,
            query_text=query_text,
            query_class=query_class,
            keyword_topic=keyword_topic,
        )
        return asdict(prompt)

    def run_site_audit(self, token: str, domain: str) -> dict:
        """GEO audit for verified domain homepage."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        self._require_verified(org.org_id, normalized)
        url = normalize_monitor_domain(normalized)
        run = self.store.create_run(org.org_id, kind="audit", domain=normalized)
        self.store.mark_run_running(run.run_id, org.org_id)
        try:
            result = run_full_audit(url, use_cache=False)
        except Exception as exc:
            failed = self.store.fail_run(run.run_id, org.org_id, error=str(exc))
            return {
                "url": url,
                "score": 0,
                "band": "failed",
                "error": (
                    "GEOSITION could not complete the live site audit right now. "
                    "Check that the verified homepage is publicly reachable and try again."
                ),
                "technical_error": str(exc)[:240],
                "recommendations": [
                    "Confirm the homepage returns a public 200 response.",
                    "Confirm robots/firewall rules allow GEOSITION to fetch the page.",
                    "Run the audit again after the site is reachable.",
                ],
                "run": asdict(failed) if failed else {},
            }

        summary = f"{len(result.recommendations[:15])} priority recommendations"
        if result.error:
            completed = self.store.fail_run(run.run_id, org.org_id, error=result.error)
        else:
            completed = self.store.complete_run(
                run.run_id,
                org.org_id,
                score=result.score,
                band=result.band,
                result_summary=summary,
            )
        return {
            "url": result.url,
            "score": result.score,
            "band": result.band,
            "error": result.error,
            "recommendations": result.recommendations[:15],
            "recommendation_evidence": result.recommendation_evidence[:15],
            "commerce": result.commerce,
            "run": asdict(completed) if completed else {},
        }

    def run_sitemap_audit(
        self,
        token: str,
        *,
        domain: str,
        sitemap_url: str = "",
        max_urls: int = 10,
    ) -> dict:
        """Run and persist a verified-domain sitemap audit immediately.

        Kept for local/dev callers; production browser flows should use
        queue_sitemap_audit() plus a worker calling run_next_sitemap_audit().
        """
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)

        max_urls = max(1, min(int(max_urls or 10), 25))
        base_url = normalize_monitor_domain(normalized)
        sitemap = sitemap_url.strip() or discover_sitemap(base_url) or f"{base_url.rstrip('/')}/sitemap.xml"
        if not url_belongs_to_domain(sitemap, normalized):
            raise ValueError("Sitemap URL must belong to the verified domain")

        run = self.store.create_run(org.org_id, kind="sitemap_audit", domain=normalized)
        self.store.mark_run_running(run.run_id, org.org_id)
        return self._execute_sitemap_audit_run(
            org_id=org.org_id,
            run_id=run.run_id,
            domain=normalized,
            sitemap_url=sitemap,
            max_urls=max_urls,
        )

    def queue_sitemap_audit(
        self,
        token: str,
        *,
        domain: str,
        sitemap_url: str = "",
        max_urls: int = 10,
    ) -> dict:
        """Queue a sitemap page audit so the browser request stays fast."""
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)

        max_urls = max(1, min(int(max_urls or 10), 25))
        base_url = normalize_monitor_domain(normalized)
        sitemap = sitemap_url.strip() or discover_sitemap(base_url) or f"{base_url.rstrip('/')}/sitemap.xml"
        if not url_belongs_to_domain(sitemap, normalized):
            raise ValueError("Sitemap URL must belong to the verified domain")

        queue_payload = {
            "kind": "sitemap_audit",
            "status": "queued",
            "sitemap_url": sitemap,
            "max_urls": max_urls,
        }
        run = self.store.create_run(
            org.org_id,
            kind="sitemap_audit",
            domain=normalized,
            status="queued",
            result_summary=json.dumps(queue_payload, separators=(",", ":")),
        )
        return {
            "status": "queued",
            "sitemap_url": sitemap,
            "max_urls": max_urls,
            "run": asdict(run),
            "pages": [
                self._page_record_dict(page)
                for page in self.store.list_page_audits(org.org_id, domain=normalized, limit=50)
            ],
            "next_step": "A GEOSITION worker will audit sitemap pages and update this dashboard.",
        }

    def run_next_sitemap_audit(self, *, domain: str = "") -> dict:
        """Claim and execute the next queued sitemap audit run."""
        claimed = self.store.claim_next_run(kind="sitemap_audit", domain=domain)
        if claimed is None:
            return {"status": "idle", "reason": "no_queued_sitemap_audit_run", "run": {}}
        payload = self._queued_sitemap_payload(claimed.result_summary)
        sitemap = str(payload.get("sitemap_url") or "").strip()
        max_urls = max(1, min(int(cast(_IntInput, payload.get("max_urls") or 10)), 25))
        try:
            return self._execute_sitemap_audit_run(
                org_id=claimed.org_id,
                run_id=claimed.run_id,
                domain=claimed.domain,
                sitemap_url=sitemap,
                max_urls=max_urls,
            )
        except Exception as exc:
            self.store.fail_run(claimed.run_id, claimed.org_id, error=str(exc))
            raise

    def _execute_sitemap_audit_run(
        self,
        *,
        org_id: int,
        run_id: int,
        domain: str,
        sitemap_url: str,
        max_urls: int,
    ) -> dict:
        try:
            result = run_batch_audit(sitemap_url, use_cache=False, max_urls=max_urls, concurrency=3)
        except Exception as exc:
            failed = self.store.fail_run(run_id, org_id, error=str(exc))
            return {
                "kind": "sitemap_audit",
                "status": "failed",
                "sitemap_url": sitemap_url,
                "discovered_urls": 0,
                "audited_urls": 0,
                "successful_urls": 0,
                "failed_urls": 0,
                "average_score": 0,
                "average_band": "failed",
                "average_score_breakdown": {},
                "pages": [],
                "top_pages": [],
                "worst_pages": [],
                "error": (
                    "GEOSITION could not audit sitemap pages right now. "
                    "Confirm the sitemap URL is public and belongs to the verified domain."
                ),
                "technical_error": str(exc)[:240],
                "run": asdict(failed) if failed else {},
            }

        pages = self._page_payloads_from_batch(result.pages)
        storage_warning = ""
        try:
            page_records = self.store.replace_page_audits(
                org_id,
                run_id=run_id,
                domain=domain,
                sitemap_url=result.sitemap_url,
                pages=pages,
            )
            page_payload = [self._page_record_dict(record) for record in page_records]
        except RuntimeError as exc:
            storage_warning = (
                "Page audit completed, but page-level storage is not ready yet. "
                "Apply the Supabase page-audit migration to save historical rows."
            )
            page_payload = pages
            storage_error = str(exc)[:240]
        else:
            storage_error = ""
        payload = {
            "kind": "sitemap_audit",
            "status": "completed",
            "sitemap_url": result.sitemap_url,
            "discovered_urls": result.discovered_urls,
            "audited_urls": result.audited_urls,
            "successful_urls": result.successful_urls,
            "failed_urls": result.failed_urls,
            "average_score": result.average_score,
            "average_band": result.average_band,
            "average_score_breakdown": result.average_score_breakdown,
            "pages": page_payload,
            "top_pages": [asdict(page) for page in result.top_pages],
            "worst_pages": [asdict(page) for page in result.worst_pages],
        }
        if storage_warning:
            payload["storage_warning"] = storage_warning
            payload["technical_error"] = storage_error
        summary = json.dumps(payload, separators=(",", ":"))
        completed = self.store.complete_run(
            run_id,
            org_id,
            score=int(round(result.average_score)),
            band=result.average_band,
            result_summary=summary,
        )
        payload["run"] = asdict(completed) if completed else {}
        return payload

    def list_page_audits(
        self,
        token: str,
        *,
        domain: str = "",
        run_id: int | None = None,
        limit: int = 100,
    ) -> dict:
        """Return durable page audit records for a verified domain."""
        user, org = self.require_session(token)
        del user
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing page audits.")
        self._require_verified(org.org_id, normalized)
        try:
            pages = self.store.list_page_audits(org.org_id, domain=normalized, run_id=run_id, limit=limit)
        except RuntimeError as exc:
            return {
                "domain": normalized,
                "pages": [],
                "warning": "Page audit storage is not ready yet. Apply the Supabase page-audit migration.",
                "technical_error": str(exc)[:240],
            }
        return {"domain": normalized, "pages": [self._page_record_dict(page) for page in pages]}

    def page_audit_history(self, token: str, *, page_url: str, limit: int = 12) -> dict:
        """Return historical page scores for one URL owned by the workspace."""
        user, org = self.require_session(token)
        del user
        page_url = page_url.strip()
        if not page_url:
            raise ValueError("page_url is required")
        domain = self._normalize_domain(urlparse(page_url).hostname or page_url)
        self._require_verified(org.org_id, domain)
        records = self.store.page_audit_history(org.org_id, page_url=page_url, limit=limit)
        return {"page_url": page_url, "history": [self._page_record_dict(record) for record in records]}

    @staticmethod
    def _page_record_dict(record) -> dict:
        payload = asdict(record)
        payload["url"] = payload.get("page_url", "")
        return payload

    @staticmethod
    def _queued_sitemap_payload(raw: str) -> dict[str, object]:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _page_payloads_from_batch(pages: list) -> list[dict[str, object]]:
        payloads = []
        for page in pages:
            raw = asdict(page)
            recommendations = [str(item) for item in raw.get("recommendations") or []]
            title_issues, meta_issues, schema_issues = PlatformService._page_issue_buckets(
                recommendations=recommendations,
                score_breakdown=dict(raw.get("score_breakdown") or {}),
            )
            payloads.append(
                {
                    "page_url": str(raw.get("url") or ""),
                    "url": str(raw.get("url") or ""),
                    "score": int(raw.get("score") or 0),
                    "band": str(raw.get("band") or ""),
                    "http_status": raw.get("http_status"),
                    "error": str(raw.get("error") or ""),
                    "score_breakdown": dict(raw.get("score_breakdown") or {}),
                    "title_issues": title_issues,
                    "meta_issues": meta_issues,
                    "schema_issues": schema_issues,
                    "recommendations": recommendations,
                }
            )
        return payloads

    @staticmethod
    def _page_issue_buckets(
        *,
        recommendations: list[str],
        score_breakdown: dict[str, object],
    ) -> tuple[list[str], list[str], list[str]]:
        title: list[str] = []
        meta: list[str] = []
        schema: list[str] = []
        for rec in recommendations:
            lowered = rec.lower()
            if "title" in lowered or "heading" in lowered or "h1" in lowered:
                title.append(rec)
            if "meta" in lowered or "description" in lowered or "robots" in lowered:
                meta.append(rec)
            if "schema" in lowered or "json-ld" in lowered or "structured data" in lowered:
                schema.append(rec)
        if _score_value(score_breakdown.get("Meta Tags")) <= 0 and not meta:
            meta.append("Review title, description, canonical, and robots meta tags.")
        if _score_value(score_breakdown.get("Schema JSON-LD")) <= 0 and not schema:
            schema.append("Add or repair JSON-LD schema so AI crawlers can classify the page.")
        return title[:5], meta[:5], schema[:5]

    def run_benchmark(
        self,
        token: str,
        *,
        domain: str,
        answers_payload: dict | list,
    ) -> dict:
        """Run domain benchmark from canonical or legacy answers JSON."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        self._require_verified(org.org_id, normalized)

        if isinstance(answers_payload, list):
            payload = {"answers": answers_payload}
        else:
            payload = answers_payload

        batch = batch_from_dict(payload)
        answer_rows = batch_to_benchmark_answers(batch)
        if not answer_rows:
            raise ValueError("No valid answers in payload")

        competitors = [c.domain for c in self.store.list_competitors(org.org_id)]
        from geo_optimizer.storage.paths import resolve_benchmark_db_path

        run = self.store.create_run(org.org_id, kind="benchmark", domain=normalized)
        self.store.mark_run_running(run.run_id, org.org_id)
        bench_db = os.environ.get("GEO_BENCHMARK_DB")
        benchmark_store = BenchmarkStore(Path(bench_db) if bench_db else resolve_benchmark_db_path())
        try:
            result = run_domain_benchmark(
                normalized,
                competitors=competitors,
                answers=answer_rows,
                audit_url=normalize_monitor_domain(normalized),
                use_cache=False,
                store=benchmark_store,
            )
        except Exception as exc:
            self.store.fail_run(run.run_id, org.org_id, error=str(exc))
            raise
        link = self.store.link_benchmark_run(
            org.org_id,
            domain=normalized,
            benchmark_run_id=result.run_id,
            benchmark_score=result.benchmark_score,
            band=result.band,
            run_at=result.run_at,
        )
        completed = self.store.complete_run(
            run.run_id,
            org.org_id,
            score=result.benchmark_score,
            band=result.band,
            external_run_id=str(result.run_id),
            result_summary=(result.executive_summary or "")[:1000],
        )
        telemetry_events = self._record_benchmark_telemetry(
            org.org_id,
            domain=normalized,
            answers=answer_rows,
            benchmark_run_id=result.run_id,
        )
        return {
            "benchmark": {
                "run_id": result.run_id,
                "score": result.benchmark_score,
                "band": result.band,
                "score_model": result.breakdown.scoring_version,
                "evidence_coverage": result.breakdown.measured_weight,
                "answers_attempted": len(batch.answers),
                "answers_included": len(answer_rows),
                "answers_unusable": len(batch.answers) - len(answer_rows),
                "score_breakdown": asdict(result.breakdown),
                "executive_summary": result.executive_summary,
                "task_gaps": [asdict(g) for g in result.task_gaps[:5]],
                "matrix_rows": [asdict(r) for r in result.competitor_matrix.rows],
            },
            "link": asdict(link),
            "run": asdict(completed) if completed else {},
            "index_events_recorded": len(telemetry_events),
        }

    def queue_hosted_collection(
        self,
        token: str,
        *,
        domain: str,
        providers: list[str] | None = None,
    ) -> dict:
        """Queue the hosted post-verification collection and benchmark bootstrap."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)

        readiness = self._collection_provider_readiness(providers)
        run = self.store.create_run(org.org_id, kind="collection", domain=normalized, status="queued")
        if not readiness["ready"]:
            completed = self.store.complete_run(
                run.run_id,
                org.org_id,
                result_summary=(
                    "Collection queued, but hosted provider credentials are missing. "
                    f"Missing: {', '.join(readiness['missing'])}."
                ),
            )
            return {
                "status": "skipped",
                "reason": "no_provider_credentials",
                "providers": readiness["available_providers"],
                "missing": readiness["missing"],
                "run": asdict(completed) if completed else {},
            }
        return {
            "status": "queued",
            "providers": readiness["available_providers"],
            "missing": [],
            "run": asdict(run),
            "next_step": "A hosted worker will collect provider answers, run the benchmark, and write Index events.",
        }

    def start_hosted_collection(
        self,
        token: str,
        *,
        domain: str,
        providers: list[str] | None = None,
    ) -> dict:
        """Backward-compatible alias for queueing hosted collection."""
        return self.queue_hosted_collection(token, domain=domain, providers=providers)

    def run_hosted_collection_now(
        self,
        token: str,
        *,
        domain: str,
        providers: list[str] | None = None,
    ) -> dict:
        """Execute hosted collection in a worker context."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)

        claimed = self.store.claim_next_run(kind="collection", domain=normalized)
        if claimed is None:
            return {"status": "idle", "reason": "no_queued_collection_run", "run": {}}
        return self._execute_claimed_collection_run(
            token,
            org_id=org.org_id,
            run_id=claimed.run_id,
            domain=normalized,
            providers=providers,
        )

    def run_next_hosted_collection(self, *, domain: str = "", providers: list[str] | None = None) -> dict:
        """Claim and execute the next queued hosted collection run."""
        claimed = self.store.claim_next_run(kind="collection", domain=domain)
        if claimed is None:
            return {"status": "idle", "reason": "no_queued_collection_run", "run": {}}
        session = self.store.create_worker_session(claimed.org_id)
        try:
            return self._execute_claimed_collection_run(
                session.token,
                org_id=claimed.org_id,
                run_id=claimed.run_id,
                domain=claimed.domain,
                providers=providers,
            )
        finally:
            self.store.delete_session(session.token)

    def _execute_claimed_collection_run(
        self,
        token: str,
        *,
        org_id: int,
        run_id: int,
        domain: str,
        providers: list[str] | None = None,
    ) -> dict:
        readiness = self._collection_provider_readiness(providers)
        if not readiness["ready"]:
            completed = self.store.complete_run(
                run_id,
                org_id,
                result_summary=(
                    "Collection ready, but no hosted provider credentials are configured. "
                    f"Missing: {', '.join(readiness['missing'])}."
                ),
            )
            return {
                "status": "skipped",
                "reason": "no_provider_credentials",
                "providers": readiness["available_providers"],
                "missing": readiness["missing"],
                "run": asdict(completed) if completed else {},
            }
        selected_providers = list(readiness["available_providers"])

        prompts = self.store.list_prompts(org_id)
        if not prompts:
            prompts = self._seed_starter_prompts(org_id, domain)

        from geo_optimizer.core.collection.normalize import batch_to_dict
        from geo_optimizer.core.collection.pipeline import collect_and_normalize
        from geo_optimizer.models.results.collection import PromptSpec

        prompt_specs = [
            PromptSpec(
                prompt_id=str(prompt.prompt_id),
                query_text=prompt.query_text,
                query_class=prompt.query_class,
                keyword_topic=prompt.keyword_topic,
                country=prompt.country,
            )
            for prompt in prompts
        ]
        try:
            batch = collect_and_normalize(
                target_domain=domain,
                prompts=prompt_specs,
                providers=selected_providers,
            )
            answers = batch_to_benchmark_answers(batch)
            successful_answers = [
                row
                for row in answers
                if row.get("parse_confidence", 0) > 0
                and not str(row.get("answer_text", "")).startswith("[collection error:")
            ]
            if not successful_answers:
                completed = self.store.complete_run(
                    run_id,
                    org_id,
                    result_summary="Collection finished, but provider responses did not produce usable answer evidence.",
                )
                return {
                    "status": "no_usable_answers",
                    "providers": selected_providers,
                    "collection_run_id": batch.collection_run_id,
                    "answers_collected": 0,
                    "answers_attempted": len(batch.answers),
                    "answers_unusable": len(batch.answers),
                    "batch": batch_to_dict(batch),
                    "run": asdict(completed) if completed else {},
                }

            benchmark = self.run_benchmark(token, domain=domain, answers_payload={"answers": successful_answers})
            completed = self.store.complete_run(
                run_id,
                org_id,
                score=int(benchmark["benchmark"]["score"]),
                band=str(benchmark["benchmark"]["band"]),
                external_run_id=str(benchmark["benchmark"]["run_id"]),
                result_summary=(
                    f"Collected {len(successful_answers)} of {len(batch.answers)} attempted answers; "
                    f"{len(batch.answers) - len(successful_answers)} could not be used."
                ),
            )
            return {
                "status": "completed",
                "providers": selected_providers,
                "collection_run_id": batch.collection_run_id,
                "answers_collected": len(successful_answers),
                "answers_attempted": len(batch.answers),
                "answers_unusable": len(batch.answers) - len(successful_answers),
                "benchmark": benchmark["benchmark"],
                "run": asdict(completed) if completed else {},
            }
        except Exception as exc:
            self.store.fail_run(run_id, org_id, error=str(exc))
            raise

    def list_runs(self, token: str, *, kind: str = "") -> dict:
        """Return recent durable platform run records for the current workspace."""
        user, org = self.require_session(token)
        return {"runs": [asdict(run) for run in self.store.list_runs(org.org_id, kind=kind)]}

    def record_agent_usage(self, token: str, *, event: dict) -> dict:
        """Record one observed AI answer/citation event for a verified domain."""
        user, org = self.require_session(token)
        domain = self._normalize_domain(str(event.get("domain", "")))
        if not domain:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, domain)

        source_type = str(event.get("source_type", "ai_answer") or "ai_answer").strip()
        if source_type not in {
            "manual_ai_answer",
            "ai_answer",
            "benchmark",
            "crawler_log",
            "retrieval_probe",
            "serp_check",
            "partner_api",
        }:
            raise ValueError(
                "source_type must be ai_answer, manual_ai_answer, benchmark, crawler_log, "
                "retrieval_probe, serp_check, or partner_api"
            )

        answer_excerpt = str(event.get("answer_excerpt", ""))
        cited_url = str(event.get("cited_url", ""))
        page_url = str(event.get("page_url", ""))
        cited_rank = self._int_or_none(event.get("cited_rank"))
        cited = self._bool_or_default(event.get("cited"), self._citation_matches_domain(cited_url, domain))
        surfaced = self._bool_or_default(
            event.get("surfaced"),
            cited
            or self._text_mentions_domain(answer_excerpt, domain)
            or self._citation_matches_domain(page_url, domain),
        )
        top_recommendation = self._bool_or_default(event.get("top_recommendation"), False)
        confidence = self._clamp_float(event.get("confidence", 1.0), 0.0, 1.0)
        value_units = self._compute_value_units(
            surfaced=surfaced,
            cited=cited,
            top_recommendation=top_recommendation,
            cited_rank=cited_rank,
            confidence=confidence,
        )
        evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
        evidence_artifact_id = str(event.get("evidence_artifact_id") or "").strip() or self._evidence_id(
            domain=domain,
            source_type=source_type,
            agent=str(event.get("agent", "")),
            query=str(event.get("query", "")),
            cited_url=cited_url,
            excerpt=answer_excerpt,
        )
        usage = self.store.record_agent_usage_event(
            org.org_id,
            domain=domain,
            page_url=page_url,
            source_type=source_type,
            agent=str(event.get("agent", "")),
            query=str(event.get("query", "")),
            answer_excerpt=answer_excerpt,
            cited_url=cited_url,
            cited_rank=cited_rank,
            surfaced=surfaced,
            cited=cited,
            top_recommendation=top_recommendation,
            confidence=confidence,
            value_units=value_units,
            evidence_artifact_id=evidence_artifact_id,
            evidence=evidence,
        )
        return {"event": asdict(usage), "summary": asdict(self.store.index_summary(org.org_id, domain=domain))}

    def import_crawler_log(self, token: str, *, domain: str, log_text: str, evidence_artifact_id: str = "") -> dict:
        """Convert passive AI crawler log lines into Index ledger events."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)

        from collections import Counter, defaultdict

        from geo_optimizer.core.log_analyzer import _match_bot, _parse_line

        visits: dict[tuple[str, str], int] = defaultdict(int)
        parsed_lines = 0
        for line in log_text.splitlines()[:100_000]:
            entry = _parse_line(line)
            if not entry:
                continue
            parsed_lines += 1
            bot = _match_bot(str(entry.get("ua", "")))
            if not bot:
                continue
            path = str(entry.get("path", "") or "/")
            visits[(bot, path)] += 1

        events = []
        for (bot, path), count in Counter(visits).most_common(50):
            page_url = (
                path
                if path.startswith(("http://", "https://"))
                else f"https://{normalized}{path if path.startswith('/') else '/' + path}"
            )
            artifact_id = evidence_artifact_id or self._evidence_id(
                domain=normalized,
                source_type="crawler_log",
                agent=bot,
                query="",
                cited_url=page_url,
                excerpt=f"{count}:{path}",
            )
            events.append(
                self.store.record_agent_usage_event(
                    org.org_id,
                    domain=normalized,
                    page_url=page_url,
                    source_type="crawler_log",
                    agent=bot,
                    query="",
                    answer_excerpt=f"{bot} crawled {path} {count} time(s).",
                    cited_url="",
                    cited_rank=None,
                    surfaced=False,
                    cited=False,
                    top_recommendation=False,
                    confidence=0.8,
                    value_units=round(min(2.0, 0.2 * count), 2),
                    evidence_artifact_id=artifact_id,
                    evidence={"path": path, "visits": count, "parsed_lines": parsed_lines},
                )
            )
        return {
            "imported_events": len(events),
            "parsed_lines": parsed_lines,
            "summary": asdict(self.store.index_summary(org.org_id, domain=normalized)),
        }

    def index_summary(self, token: str, *, domain: str = "") -> dict:
        """Return the content-owner Index telemetry summary."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing Index telemetry.")
        self._require_verified(org.org_id, normalized)
        return {"summary": asdict(self.store.index_summary(org.org_id, domain=normalized))}

    def value_ledger(self, token: str, *, domain: str = "") -> dict:
        """Return attribution accounting before any payout or licensing layer exists."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing the value ledger.")
        self._require_verified(org.org_id, normalized)
        summary = self.store.index_summary(org.org_id, domain=normalized)
        return {
            "domain": normalized,
            "citation_value_units": summary.total_value_units,
            "source_coverage": summary.source_coverage,
            "attribution_ready": summary.cited_events > 0 or summary.source_coverage.get("crawler_log", 0) > 0,
            "compensation_status": "ledger_only",
            "payouts_enabled": False,
            "basis": [
                "citation rank",
                "top recommendation",
                "answer/crawler source type",
                "confidence",
                "repeat occurrence",
            ],
        }

    def retrieval_probe(self, token: str, *, domain: str, query: str) -> dict:
        """Probe the current evidence ledger as a lightweight retrieval substrate."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("domain is required")
        self._require_verified(org.org_id, normalized)
        terms = {part for part in query.lower().split() if len(part) > 2}
        events = self.store.list_agent_usage_events(org.org_id, domain=normalized, limit=1000)
        candidates = []
        for event in events:
            haystack = " ".join([event.query, event.answer_excerpt, event.page_url, event.cited_url]).lower()
            overlap = len([term for term in terms if term in haystack])
            if overlap:
                candidates.append(
                    {
                        "page_url": event.cited_url or event.page_url,
                        "agent": event.agent,
                        "source_type": event.source_type,
                        "evidence_artifact_id": event.evidence_artifact_id,
                        "score": round(overlap / max(1, len(terms)), 3),
                    }
                )
        candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:10]
        self.store.record_agent_usage_event(
            org.org_id,
            domain=normalized,
            page_url=str(candidates[0]["page_url"]) if candidates else "",
            source_type="retrieval_probe",
            agent="geosition",
            query=query,
            answer_excerpt=f"Retrieval probe returned {len(candidates)} candidate(s).",
            cited_url=str(candidates[0]["page_url"]) if candidates else "",
            surfaced=bool(candidates),
            cited=False,
            top_recommendation=False,
            confidence=0.6,
            value_units=0.6 if candidates else 0.0,
            evidence_artifact_id=self._evidence_id(
                domain=normalized,
                source_type="retrieval_probe",
                agent="geosition",
                query=query,
                cited_url=str(candidates[0]["page_url"]) if candidates else "",
                excerpt=str(candidates),
            ),
            evidence={"candidate_count": len(candidates), "terms": sorted(terms)},
        )
        return {
            "domain": normalized,
            "query": query,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "gaps": [] if candidates else ["No matching cited/crawled evidence found for this query."],
        }

    def run_serp_check(self, token: str, *, domain: str, keyword: str) -> dict:
        """Run an automated organic SERP check and record top-list-position evidence."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("domain is required")
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword is required")
        self._require_verified(org.org_id, normalized)

        run = self.store.create_run(org.org_id, kind="serp_check", domain=normalized)
        self.store.mark_run_running(run.run_id, org.org_id)
        try:
            from bs4 import BeautifulSoup

            from geo_optimizer.utils.http import fetch_url

            response, fetch_error = fetch_url(normalize_monitor_domain(normalized), timeout=15)
            page_soup = (
                BeautifulSoup(response.text, "html.parser") if response is not None and not fetch_error else None
            )
            serp = audit_serp(
                page_soup,
                normalize_monitor_domain(normalized),
                keyword=keyword,
            )
            if fetch_error:
                serp.issues.append(f"Homepage fetch skipped for page gap analysis: {fetch_error}")
        except Exception as exc:
            self.store.fail_run(run.run_id, org.org_id, error=str(exc))
            raise

        match = None
        for competitor in serp.competitors:
            if self._citation_matches_domain(competitor.url, normalized):
                match = competitor
                break
        rank = int(match.rank) if match else None
        surfaced = match is not None
        top_list_position = bool(rank == 1)
        confidence = 0.9 if serp.checked and not serp.issues else 0.55
        cited_url = match.url if match else ""
        event = self.store.record_agent_usage_event(
            org.org_id,
            domain=normalized,
            page_url=cited_url,
            source_type="serp_check",
            agent=serp.search_engine or "organic_serp",
            query=keyword,
            answer_excerpt=(
                f"SERP check found {normalized} at organic rank #{rank}."
                if rank
                else f"SERP check did not find {normalized} in the first-page results."
            ),
            cited_url=cited_url,
            cited_rank=rank,
            surfaced=surfaced,
            cited=False,
            top_recommendation=False,
            confidence=confidence,
            value_units=self._compute_value_units(
                surfaced=surfaced,
                cited=False,
                top_recommendation=False,
                cited_rank=rank,
                confidence=confidence,
            ),
            evidence_artifact_id=self._evidence_id(
                domain=normalized,
                source_type="serp_check",
                agent=serp.search_engine or "organic_serp",
                query=keyword,
                cited_url=cited_url,
                excerpt="|".join(c.url for c in serp.competitors[:10]),
            ),
            evidence={
                "search_engine": serp.search_engine,
                "checked": serp.checked,
                "keyword": keyword,
                "organic_rank": rank,
                "top_list_position_pass": top_list_position,
                "result_count": len(serp.competitors),
                "issues": serp.issues,
                "top_results": [
                    {
                        "rank": competitor.rank,
                        "url": competitor.url,
                        "title": competitor.title,
                    }
                    for competitor in serp.competitors[:10]
                ],
            },
        )
        completed = self.store.complete_run(
            run.run_id,
            org.org_id,
            score=max(0, 100 - ((rank or 11) - 1) * 10),
            band="top" if rank == 1 else "visible" if rank else "missed",
            result_summary=(
                f"Organic rank #{rank} for {keyword}."
                if rank
                else f"No first-page organic position found for {keyword}."
            ),
        )
        return {
            "domain": normalized,
            "keyword": keyword,
            "organic_rank": rank,
            "top_list_position_pass": top_list_position,
            "search_engine": serp.search_engine,
            "issues": serp.issues,
            "event": asdict(event),
            "run": asdict(completed) if completed else {},
            "summary": asdict(self.store.index_summary(org.org_id, domain=normalized)),
        }

    def benchmark_harness(self) -> dict:
        """Public description of the empirical Index benchmark contract."""
        return {
            "name": "GEOSITION Index retrieval and citation harness",
            "status": "public_contract",
            "metrics": [
                "citation_accuracy",
                "retrieval_freshness",
                "source_diversity",
                "cost_per_query",
                "citation_rank_stability",
                "answer_reproducibility",
            ],
            "event_sources": ["ai_answer", "benchmark", "crawler_log", "retrieval_probe", "serp_check", "partner_api"],
            "output": "per-domain citation position, evidence artifacts, trend deltas, and fix priority",
        }

    def collection_status(self, token: str, *, domain: str = "") -> dict:
        """Return hosted collection readiness for the verified workspace."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing collection status.")
        self._require_verified(org.org_id, normalized)
        readiness = self._collection_provider_readiness()
        return {
            "domain": normalized,
            "auto_collection_on_verify": self._auto_collection_enabled(),
            "available_providers": readiness["available_providers"],
            "ready": readiness["ready"],
            "missing": readiness["missing"],
            "latest_collection_runs": [asdict(run) for run in self.store.list_runs(org.org_id, kind="collection")[:5]],
        }

    def public_index_preview(self, domain: str) -> dict:
        """Public, no-network domain preview for the Index claim funnel."""
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("domain is required")
        claim = self.store.domain_claim_status(normalized)
        return {
            "domain": normalized,
            "claimed": bool(claim["claimed"]),
            "verified": bool(claim["verified"]),
            "claim_path": f"/platform/register?domain={normalized}",
            "preview": {
                "telemetry": "locked_until_verified",
                "available_after_claim": [
                    "AI answer usage ledger",
                    "Citation share and top recommendation rate",
                    "Citation value units",
                    "Benchmark-derived agent evidence",
                    "Fix priority from content-brief gatekeepers",
                ],
            },
        }

    def citation_share_summary(self, token: str, *, domain: str = "") -> dict:
        """Return latest AI-answer monitoring summary for a verified domain."""
        user, org = self.require_session(token)
        normalized = self._normalize_domain(domain or self._primary_domain(org.org_id))
        if not normalized:
            raise ValueError("Add and verify a domain before viewing citation share.")
        self._require_verified(org.org_id, normalized)

        from geo_optimizer.storage.paths import resolve_benchmark_db_path

        bench_db = os.environ.get("GEO_BENCHMARK_DB")
        benchmark_store = BenchmarkStore(Path(bench_db) if bench_db else resolve_benchmark_db_path())
        summary = benchmark_store.get_latest_citation_share_summary(normalized)
        if summary is None:
            return {
                "domain": normalized,
                "has_data": False,
                "message": "Run an AI benchmark to start monitoring citation share.",
            }
        return {
            "has_data": True,
            "summary": asdict(summary),
        }

    def require_verified_domain(self, token: str, domain: str) -> str:
        """Authenticate and return a domain verified by this workspace."""
        _, org = self.require_session(token)
        normalized = self._normalize_domain(domain)
        self._require_verified(org.org_id, normalized)
        return normalized

    def _require_verified(self, org_id: int, domain: str) -> None:
        for record in self.store.list_domains(org_id):
            if record.domain == domain and record.status == "verified":
                return
        raise ValueError(f"Domain {domain} is not verified. Complete DNS or HTTPS verification first.")

    def _require_any_verified_domain(self, org_id: int) -> None:
        """Workspace features need at least one verified website domain."""
        for record in self.store.list_domains(org_id):
            if record.status == "verified":
                return
        raise ValueError("Verify a website domain before using standings, citations, audits, or benchmarks.")

    def _primary_domain(self, org_id: int) -> str:
        """Return the first verified domain, falling back to the first added domain."""
        domains = self.store.list_domains(org_id)
        for record in domains:
            if record.status == "verified":
                return cast(str, record.domain)
        return cast(str, domains[0].domain) if domains else ""

    def _record_benchmark_telemetry(
        self,
        org_id: int,
        *,
        domain: str,
        answers: list[dict],
        benchmark_run_id: int,
    ) -> list:
        """Convert benchmark answer evidence into Index usage events."""
        events = []
        for row in answers:
            answer_text = str(row.get("answer_text", ""))
            citations = extract_citations(answer_text, extra_urls=row.get("citation_urls"))
            target_citations = [
                citation for citation in citations if self._citation_matches_domain(citation.url, domain)
            ]
            first = target_citations[0] if target_citations else None
            cited_rank = first.position if first else None
            cited = bool(first)
            surfaced = cited or self._text_mentions_domain(answer_text, domain)
            # Citation order does not establish recommendation rank.
            top_recommendation = False
            confidence = self._clamp_float(row.get("parse_confidence", 1.0), 0.0, 1.0)
            events.append(
                self.store.record_agent_usage_event(
                    org_id,
                    domain=domain,
                    page_url=first.url if first else "",
                    source_type="benchmark",
                    agent=str(row.get("provider", "")),
                    query=str(row.get("prompt") or row.get("query_text", "")),
                    answer_excerpt=answer_text[:1000],
                    cited_url=first.url if first else "",
                    cited_rank=cited_rank,
                    surfaced=surfaced,
                    cited=cited,
                    top_recommendation=top_recommendation,
                    confidence=confidence,
                    value_units=self._compute_value_units(
                        surfaced=surfaced,
                        cited=cited,
                        top_recommendation=top_recommendation,
                        cited_rank=cited_rank,
                        confidence=confidence,
                    ),
                    evidence_artifact_id=self._evidence_id(
                        domain=domain,
                        source_type="benchmark",
                        agent=str(row.get("provider", "")),
                        query=str(row.get("prompt") or row.get("query_text", "")),
                        cited_url=first.url if first else "",
                        excerpt=answer_text,
                    ),
                    evidence={
                        "benchmark_run_id": benchmark_run_id,
                        "citation_count": len(citations),
                        "target_citation_count": len(target_citations),
                    },
                )
            )
        return events

    @staticmethod
    def _evidence_id(*, domain: str, source_type: str, agent: str, query: str, cited_url: str, excerpt: str) -> str:
        raw = "\n".join([domain, source_type, agent, query, cited_url, excerpt[:500]])
        return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _normalize_domain(self, domain: str) -> str:
        raw = domain.strip().lower()
        if raw.startswith(("http://", "https://")):
            return (urlparse(raw).hostname or raw).lower()
        return raw.split("/")[0].split(":")[0]

    @staticmethod
    def _normalize_verifiable_domain(domain: str) -> str:
        raw = domain.strip().lower()
        if not raw or any(char.isspace() for char in raw):
            raise ValueError("Enter a valid website domain, like example.com")
        if "@" in raw:
            raise ValueError("Domain must not include usernames, passwords, or email addresses")

        if raw.startswith(("http://", "https://")):
            parsed = urlparse(raw)
            if "@" in (parsed.netloc or ""):
                raise ValueError("Domain must not include usernames or passwords")
            host = (parsed.hostname or "").rstrip(".").lower()
        else:
            host = raw.split("/", 1)[0].split(":", 1)[0].rstrip(".")

        if not host or host in {"localhost", "metadata", "metadata.google.internal"}:
            raise ValueError("Enter a public website domain, like example.com")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("Enter a website domain instead of an IP address")

        labels = host.split(".")
        if len(labels) < 2 or len(host) > 253 or any(not _DOMAIN_LABEL_RE.match(label) for label in labels):
            raise ValueError("Enter a valid website domain, like example.com")
        return host

    def _citation_matches_domain(self, url: str, domain: str) -> bool:
        if not url:
            return False
        host = self._normalize_domain(url)
        host_key = self._domain_key(host)
        domain_key = self._domain_key(domain)
        return host_key == domain_key or host_key.endswith(f".{domain_key}")

    def _text_mentions_domain(self, text: str, domain: str) -> bool:
        if not text or not domain:
            return False
        lowered = text.lower()
        key = self._domain_key(domain)
        return domain.lower() in lowered or key in lowered

    @staticmethod
    def _domain_key(domain: str) -> str:
        return domain[4:] if domain.startswith("www.") else domain

    @staticmethod
    def _int_or_none(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            parsed = int(cast(_IntInput, value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _bool_or_default(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    @staticmethod
    def _clamp_float(value: object, minimum: float, maximum: float) -> float:
        try:
            parsed = float(cast(_FloatInput, value))
        except (TypeError, ValueError):
            parsed = maximum
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _compute_value_units(
        *,
        surfaced: bool,
        cited: bool,
        top_recommendation: bool,
        cited_rank: int | None,
        confidence: float,
    ) -> float:
        """Estimate contribution value before real pricing or revenue share exists."""
        units = 0.0
        if surfaced:
            units += 1.0
        if cited:
            units += 3.0
        if top_recommendation:
            units += 5.0
        if cited_rank:
            units += max(0.5, 4.0 / cited_rank)
        return round(units * confidence, 2)

    @staticmethod
    def _auto_collection_enabled() -> bool:
        return os.environ.get("GEOSITION_AUTO_COLLECTION_ON_VERIFY", "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _available_collection_providers() -> list[str]:
        providers = []
        if os.environ.get("PERPLEXITY_API_KEY", "").strip():
            providers.append("perplexity")
        if os.environ.get("GEMINI_API_KEY", "").strip():
            providers.append("gemini")
        configured = [
            item.strip().lower()
            for item in os.environ.get("GEOSITION_COLLECTION_PROVIDERS", "").split(",")
            if item.strip()
        ]
        return configured or providers

    @staticmethod
    def _provider_missing_credentials(provider: str) -> list[str]:
        if provider == "perplexity":
            return [] if os.environ.get("PERPLEXITY_API_KEY", "").strip() else ["PERPLEXITY_API_KEY"]
        if provider == "gemini":
            return [] if os.environ.get("GEMINI_API_KEY", "").strip() else ["GEMINI_API_KEY"]
        return [f"unsupported provider: {provider}"]

    @classmethod
    def _collection_provider_readiness(cls, providers: list[str] | None = None) -> _ProviderReadiness:
        selected = providers or cls._available_collection_providers()
        available = []
        missing = []
        for provider in selected:
            normalized = provider.strip().lower()
            if not normalized:
                continue
            gaps = cls._provider_missing_credentials(normalized)
            if gaps:
                missing.extend(gaps)
                continue
            available.append(normalized)
        if not selected:
            missing.append("PERPLEXITY_API_KEY or GEMINI_API_KEY")
        return {
            "available_providers": available,
            "missing": sorted(set(missing)),
            "ready": bool(available) and not missing,
        }

    def _seed_starter_prompts(self, org_id: int, domain: str) -> list:
        brand = self._domain_key(domain).split(".", 1)[0].replace("-", " ").strip() or domain
        prompts = [
            self.store.add_prompt(
                org_id,
                external_id="starter-brand",
                query_text=f"What is {brand} best for?",
                query_class="brand_discovery",
                keyword_topic=brand,
            ),
            self.store.add_prompt(
                org_id,
                external_id="starter-vendor",
                query_text=f"Best alternatives and competitors to {brand}",
                query_class="vendor_selection",
                keyword_topic=brand,
            ),
        ]
        return prompts

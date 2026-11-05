"""Tests for GEOSITION Platform SaaS layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from geo_optimizer.saas.auth import hash_password, verify_password
from geo_optimizer.saas.domain_verify import verify_https_file
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.saas.supabase_store import SupabasePlatformStore

_PLATFORM_TEMPLATE_DIR = Path("src/geo_optimizer/web/templates/platform")


def test_password_hash_roundtrip():
    stored = hash_password("secure-password-1")
    assert verify_password("secure-password-1", stored)
    assert not verify_password("wrong", stored)


def test_https_domain_verification_uses_safe_fetch_contract():
    class Response:
        text = "geo-verify=test-token\n"

    with (
        patch("geo_optimizer.saas.domain_verify.validate_public_url", return_value=(True, None)) as validate,
        patch(
            "geo_optimizer.saas.domain_verify.fetch_url",
            return_value=(Response(), None),
        ) as fetch,
    ):
        ok, message = verify_https_file("example.com", "test-token")

    assert ok is True
    assert message == "HTTPS well-known file verified"
    validate.assert_called_once_with("https://example.com/.well-known/geo-verify.txt")
    fetch.assert_called_once_with("https://example.com/.well-known/geo-verify.txt", timeout=15)


def test_https_domain_verification_reports_safe_fetch_failure():
    with (
        patch("geo_optimizer.saas.domain_verify.validate_public_url", return_value=(True, None)),
        patch(
            "geo_optimizer.saas.domain_verify.fetch_url",
            return_value=(None, "Timeout"),
        ),
    ):
        ok, message = verify_https_file("example.com", "test-token")

    assert ok is False
    assert message == "Timeout"


@pytest.mark.parametrize("email", ["user@gmail.com", "owner@outlook.com"])
def test_register_allows_consumer_email_accounts(tmp_path, email):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email=email, password="password123", org_name="Client")
    logged_in = service.login(email=email, password="password123")

    assert registered["user"]["email"] == email
    assert logged_in["user"]["email"] == email


def test_register_and_session(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@acme-corp.test", password="password123", org_name="Acme")
    token = out["session"]["token"]
    dash = service.dashboard(token)
    assert dash.organization.email_domain == "acme-corp.test"
    assert dash.user.email == "owner@acme-corp.test"


def test_dashboard_agency_loop_advances_from_saved_evidence(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@example.com", password="password123", org_name="Example")
    token = out["session"]["token"]
    domain = service.add_website_domain(token, "example.com")["domain"]

    locked = service.dashboard(token).agency_loop
    assert locked.current_step == "verify"
    assert locked.next_action == "Verify domain"

    store.mark_domain_verified(domain["domain_id"], method="test")
    verified = service.dashboard(token).agency_loop
    assert verified.current_step == "pages"
    assert verified.next_action == "Run page audit"

    org_id = service.dashboard(token).organization.org_id
    run = store.create_run(org_id, kind="sitemap_audit", domain="example.com", status="completed")
    store.replace_page_audits(
        org_id,
        run_id=run.run_id,
        domain="example.com",
        sitemap_url="https://example.com/sitemap.xml",
        pages=[{"page_url": "https://example.com/", "score": 76, "band": "good"}],
    )
    with_pages = service.dashboard(token).agency_loop
    assert with_pages.current_step == "benchmark"
    assert with_pages.next_action == "Run benchmark"

    store.link_benchmark_run(
        org_id,
        domain="example.com",
        benchmark_run_id=1,
        benchmark_score=72,
        band="good",
        run_at="2026-06-12T00:00:00+00:00",
    )
    with_benchmark = service.dashboard(token).agency_loop
    assert with_benchmark.current_step == "skill"
    assert with_benchmark.next_action == "Copy Skill Files"

    store.create_weekly_evidence_run(
        org_id,
        domain="example.com",
        period_start="2026-06-05T00:00:00+00:00",
        period_end="2026-06-12T00:00:00+00:00",
        score=82,
        band="good",
        summary="Weekly proof",
    )
    with_report = service.dashboard(token).agency_loop
    assert with_report.current_step == "report"
    assert with_report.next_action == "Record AI visibility evidence"
    assert [step.state for step in with_report.steps].count("current") == 1


def test_storage_health_reports_page_and_weekly_tables(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@storage-health.test", password="password123", org_name="Storage Health")
    token = out["session"]["token"]

    health = service.storage_health(token)
    tables = {str(item["table"]): item for item in health["tables"]}

    assert health["ok"] is True
    assert tables["page_audits"]["ok"] is True
    assert tables["weekly_evidence_runs"]["ok"] is True


def test_platform_production_health_endpoint_reports_deploy_checklist(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEOSITION_WORKER_TOKEN", "worker-secret")
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://geositionai.com")
    monkeypatch.setenv("GEOSITION_PLUNK_API_KEY", "plunk-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    unauthorized = client.get("/api/v1/platform/health")
    response = client.get("/api/v1/platform/health", headers={"X-GEOSITION-Worker-Token": "worker-secret"})

    assert unauthorized.status_code == 403
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["storage"]["ok"] is True
    assert payload["checks"]["password_reset"]["ready"] is True
    assert payload["checks"]["password_reset"]["configured_modes"] == ["plunk"]
    assert payload["checks"]["worker"]["configured"] is True
    assert "gemini" in payload["checks"]["providers"]["available_providers"]


def test_platform_production_health_endpoint_flags_missing_critical_config(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEOSITION_WORKER_TOKEN", "worker-secret")
    monkeypatch.delenv("GEOSITION_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("GEOSITION_PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    response = client.get("/api/v1/platform/health", headers={"X-GEOSITION-Worker-Token": "worker-secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"]["password_reset"]["ready"] is False
    assert payload["checks"]["providers"]["ready"] is False
    assert any("password reset" in action.lower() for action in payload["next_actions"])


def test_dashboard_tolerates_missing_optional_tables(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@partial-migration.test", password="password123", org_name="Partial")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "partial-migration.test")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    def missing_table(*_args, **_kwargs):
        raise RuntimeError("Supabase GET optional table failed: relation does not exist")

    monkeypatch.setattr(store, "list_page_audits", missing_table)
    monkeypatch.setattr(store, "list_weekly_evidence_runs", missing_table)
    monkeypatch.setattr(store, "index_summary", missing_table)

    dash = service.dashboard(token)

    assert dash.primary_verified_domain == "partial-migration.test"
    assert dash.recent_page_audits == []
    assert dash.recent_weekly_reports == []
    assert dash.index_summary.total_events == 0


def test_password_reset_updates_password_and_invalidates_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@resetco.test", password="password123", org_name="ResetCo")
    old_token = out["session"]["token"]

    reset = service.request_password_reset(email="owner@resetco.test", base_url="http://testserver")
    assert reset["ok"] is True
    assert reset["reset_url"].startswith("http://testserver/platform/reset-password?token=")
    reset_token = reset["reset_url"].split("token=", 1)[1]

    service.reset_password(token=reset_token, password="new-password123")

    with pytest.raises(PermissionError, match="Invalid or expired session"):
        service.dashboard(old_token)
    with pytest.raises(ValueError, match="Invalid email or password"):
        service.login(email="owner@resetco.test", password="password123")

    logged_in = service.login(email="owner@resetco.test", password="new-password123")
    assert logged_in["user"]["email"] == "owner@resetco.test"

    with pytest.raises(ValueError, match="Invalid or expired reset link"):
        service.reset_password(token=reset_token, password="another-password123")


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/auth/register", {"email": "owner@example.com", "password": "password123", "org_name": "Example"}),
        ("/api/v1/auth/login", {"email": "owner@example.com", "password": "password123"}),
        ("/api/v1/auth/forgot-password", {"email": "owner@example.com"}),
        ("/api/v1/auth/reset-password", {"token": "reset-token", "password": "password123"}),
    ],
)
def test_auth_routes_return_json_when_platform_storage_is_unavailable(path, payload, monkeypatch):
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    def fail_service():
        raise RuntimeError(
            "Vercel platform auth requires durable Supabase storage. Set SUPABASE_URL or "
            "NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )

    monkeypatch.setattr(platform_routes, "_get_service", fail_service)
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    response = client.post(path, json=payload)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert "SUPABASE_SERVICE_ROLE_KEY" in response.json()["detail"]


def test_platform_write_routes_return_json_when_storage_fails(tmp_path, monkeypatch):
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    db = tmp_path / "platform.db"
    service = PlatformService(PlatformStore(db))
    platform_routes._service = service
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    token = registered["session"]["token"]

    def fail_add_competitor(*_args, **_kwargs):
        raise RuntimeError("Supabase POST geo_org_competitors failed")

    monkeypatch.setattr(service, "add_competitor", fail_add_competitor)
    client = TestClient(web_app.app)

    response = client.post(
        "/api/v1/competitors",
        json={"domain": "rival.example"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Platform storage is unavailable. Check the server database configuration and try again."


def test_platform_auth_templates_parse_non_json_api_errors():
    for template_name in ["login.html", "register.html", "forgot-password.html", "reset-password.html", "dashboard.html"]:
        html = (_PLATFORM_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        assert "async function readApiResponse" in html
        assert "await res.json()" not in html


def test_platform_production_smoke_script_covers_deploy_kpis():
    script = Path("scripts/platform-production-smoke.py").read_text(encoding="utf-8")

    assert "/api/v1/auth/register" in script
    assert "/api/v1/auth/login" in script
    assert "/api/v1/domains" in script
    assert "/api/v1/platform/health" in script
    assert "/api/v1/audit" in script
    assert "/api/v1/auth/forgot-password" in script
    assert "--require-verified" in script
    assert "GEOSITION_SMOKE_DOMAIN" in script


def test_dashboard_includes_skill_files_copy_prompt():
    html = (_PLATFORM_TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "Copy Skill Files" in html
    assert "SKILL_FILES_CONTEXT" in html
    assert "Cursor, Claude, or any AI tool" in html
    assert "Paid access is for recurring GEOSITION AI automation" in html


def test_dashboard_explains_first_run_loop_and_report_deltas():
    html = (_PLATFORM_TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "First run loop" in html
    assert "Verify domain" in html
    assert "Run page audit" in html
    assert "Run benchmark" in html
    assert "Copy skill files" in html
    assert "Fix the pages" in html
    assert "Re-run and prove delta" in html
    assert "before/after by URL and prompt" in html


def test_dashboard_product_loop_keeps_locked_skill_copy_on_verify_gate():
    html = (_PLATFORM_TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")
    loop_js = (_PLATFORM_TEMPLATE_DIR / "assets" / "dashboard-loop.js").read_text(encoding="utf-8")

    assert "/platform/assets/dashboard-loop.js" in html
    assert "function applySkillFileTransition(blocked)" in html
    assert "function markSkillFilesCopied()" in html
    assert "function markSkillFilesBlocked()" in html
    assert "document.body.classList.contains('workspace-locked')" in html
    assert "skillCopyTransitions(locked, blocked)" in html
    assert "deriveAgencyLoop" in loop_js
    assert "data-agency-next-action" in html
    assert "{ step: 'verify', state: 'current', label: 'Verify next' }" in loop_js
    assert "{ step: 'fix', state: 'current', label: 'Fix next' }" in loop_js
    assert "blocked ? 'Selected' : 'Copied'" in loop_js
    assert "document.querySelectorAll('[data-product-step]').forEach" in html
    assert "other.classList.remove('is-current')" in html


def test_landing_offers_a_public_audit_without_pricing_section():
    html = (_PLATFORM_TEMPLATE_DIR / "landing.html").read_text(encoding="utf-8")

    assert "Built first for agencies" not in html
    assert "Client GEO visibility" not in html
    assert 'href="#agencies"' not in html
    assert 'id="domain-form"' in html
    assert "'/demo?url='" in html
    assert 'id="pricing"' not in html


def test_platform_report_renderers_surface_url_and_prompt_deltas():
    from geo_optimizer.saas.models import WeeklyEvidenceRun
    from geo_optimizer.web import platform_routes

    page_html = platform_routes._sitemap_pages_html(
        [
            {
                "page_url": "https://example.com/service",
                "score": 81,
                "previous_score": 62,
                "score_delta": 19,
                "band": "good",
                "recommendations": ["Add explicit pricing and fresh proof."],
            }
        ]
    )
    weekly_html = platform_routes._weekly_report_item(
        WeeklyEvidenceRun(domain="example.com", status="completed", score=81, summary="Weekly proof")
    )

    assert "Before 62/100 -> after 81/100" in page_html
    assert "delta +19" in page_html
    assert "Before/after deltas by URL and prompt" in weekly_html


def test_password_reset_unknown_email_is_generic(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)

    reset = service.request_password_reset(email="missing@resetco.test", base_url="http://testserver")

    assert reset["ok"] is True
    assert "reset_url" not in reset


def test_password_reset_sends_email_when_smtp_is_configured(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    service.register(email="owner@mailco.test", password="password123", org_name="MailCo")
    monkeypatch.delenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("GEOSITION_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("GEOSITION_SMTP_PORT", "2525")
    monkeypatch.setenv("GEOSITION_SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("GEOSITION_SMTP_PASSWORD", "smtp-pass")
    monkeypatch.setenv("GEOSITION_SMTP_FROM", "support@geosition.test")
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://app.example")

    with patch("geo_optimizer.saas.service.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value.__enter__.return_value
        reset = service.request_password_reset(email="owner@mailco.test", base_url="https://app.example")

    assert reset["ok"] is True
    assert reset["delivery"] == "email"
    assert "reset_url" not in reset
    smtp_cls.assert_called_once_with("smtp.example.test", 2525, timeout=15)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("smtp-user", "smtp-pass")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "owner@mailco.test"
    assert message["From"] == "support@geosition.test"
    assert "https://app.example/platform/reset-password?token=" in message.get_content()


def test_password_reset_sends_webhook_without_smtp(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    service.register(email="owner@webhookmail.test", password="password123", org_name="Webhook Mail")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("GEOSITION_PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", "https://mail.example.test/reset")
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_FROM", "support@geosition.test")
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://app.example")

    with patch("geo_optimizer.saas.service.requests.post") as post:
        post.return_value.status_code = 202
        post.return_value.text = ""
        reset = service.request_password_reset(email="owner@webhookmail.test", base_url="https://app.example")

    assert reset["ok"] is True
    assert reset["delivery"] == "webhook"
    assert "reset_url" not in reset
    post.assert_called_once()
    url = post.call_args.args[0]
    assert url == "https://mail.example.test/reset"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer hook-secret"
    body = post.call_args.kwargs["json"]
    assert body["to"] == "owner@webhookmail.test"
    assert body["from"] == "support@geosition.test"
    assert body["subject"] == "Reset your GEOSITION password"
    assert body["reset_url"].startswith("https://app.example/platform/reset-password?token=")
    assert body["reset_url"] in body["text"]
    assert "Choose a new password" in body["html"]


def test_password_reset_sends_plunk_without_smtp_or_webhook(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    service.register(email="owner@plunkmail.test", password="password123", org_name="Plunk Mail")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    monkeypatch.delenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("GEOSITION_PLUNK_API_KEY", "plunk-secret")
    monkeypatch.setenv("GEOSITION_PLUNK_API_URL", "https://plunk.example.test/v1/send")
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_FROM", "support@geosition.test")
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://app.example")

    with patch("geo_optimizer.saas.service.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.text = '{"success":true}'
        reset = service.request_password_reset(email="owner@plunkmail.test", base_url="https://app.example")

    assert reset["ok"] is True
    assert reset["delivery"] == "plunk"
    assert "reset_url" not in reset
    post.assert_called_once()
    url = post.call_args.args[0]
    assert url == "https://plunk.example.test/v1/send"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer plunk-secret"
    body = post.call_args.kwargs["json"]
    assert body["to"] == "owner@plunkmail.test"
    assert body["from"] == "support@geosition.test"
    assert body["subject"] == "Reset your GEOSITION password"
    assert body["subscribed"] is False
    assert body["data"]["reset_url"]["persistent"] is False
    assert body["data"]["reset_url"]["value"].startswith("https://app.example/platform/reset-password?token=")
    assert "Choose a new password" in body["body"]


def test_password_reset_does_not_expose_development_link_on_vercel(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    service.register(email="owner@hostedreset.test", password="password123", org_name="Hosted Reset")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    monkeypatch.delenv("GEOSITION_PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", raising=False)

    reset = service.request_password_reset(email="owner@hostedreset.test", base_url="https://app.example")

    assert reset["ok"] is True
    assert reset["delivery"] == "email_unconfigured"
    assert "reset_url" not in reset
    assert reset["message"] == "Password reset email is not configured yet. Contact support."


def test_consumer_email_account_can_add_owned_website_domain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@gmail.com", password="password123", org_name="Velora")
    token = out["session"]["token"]
    info = service.add_website_domain(token, "velora.example")

    assert info["domain"]["domain"] == "velora.example"
    assert info["dns_host"] == "_geo-verify.velora.example"
    assert info["dns_value"].startswith("geo-verify=")


def test_add_website_domain_accepts_full_url_and_normalizes_host(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@gmail.com", password="password123", org_name="Velora")
    token = out["session"]["token"]

    info = service.add_website_domain(token, "https://www.velora.example/pricing?ref=geo")

    assert info["domain"]["domain"] == "www.velora.example"
    assert info["dns_host"] == "_geo-verify.www.velora.example"


def test_add_website_domain_rejects_invalid_or_internal_hosts(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@gmail.com", password="password123", org_name="Velora")
    token = out["session"]["token"]

    for domain in ["", "bad domain.test", "localhost", "127.0.0.1", "https://user:pass@velora.example"]:
        with pytest.raises(ValueError):
            service.add_website_domain(token, domain)


def test_platform_store_generated_prompt_ids_are_stable_and_idempotent(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    org_id = registered["organization"]["org_id"]

    first = store.add_prompt(org_id, external_id="", query_text="Best AI visibility platform?")
    second = store.add_prompt(org_id, external_id="", query_text="Best AI visibility platform?")

    assert first.external_id == second.external_id
    assert first.prompt_id == second.prompt_id
    assert [prompt.query_text for prompt in store.list_prompts(org_id)] == ["Best AI visibility platform?"]


def test_platform_store_duplicate_domain_and_competitor_writes_are_idempotent(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    org_id = registered["organization"]["org_id"]

    first_domain = store.add_domain(org_id, "example.com", "first-token")
    second_domain = store.add_domain(org_id, "https://example.com/path", "second-token")
    first_competitor = store.add_competitor(org_id, "rival.example")
    second_competitor = store.add_competitor(org_id, "https://rival.example/page")

    assert first_domain.domain_id == second_domain.domain_id
    assert second_domain.verify_token == "second-token"
    assert [domain.domain for domain in store.list_domains(org_id)] == ["example.com"]
    assert first_competitor.competitor_id == second_competitor.competitor_id
    assert [competitor.domain for competitor in store.list_competitors(org_id)] == ["rival.example"]


def test_supabase_prompt_write_updates_existing_generated_external_id(monkeypatch):
    store = object.__new__(SupabasePlatformStore)
    calls = []

    def fake_request(method, table, *, params=None, json_body=None, prefer="return=representation"):
        calls.append({"method": method, "table": table, "params": params, "json_body": json_body, "prefer": prefer})
        if method == "GET":
            return [
                {
                    "id": 42,
                    "org_id": 7,
                    "external_id": str(params["external_id"]).replace("eq.", "", 1),
                    "query_text": "Old prompt",
                    "query_class": "",
                    "keyword_topic": "",
                    "persona": "",
                    "country": "",
                }
            ]
        if method == "PATCH":
            return [
                {
                    "id": 42,
                    "org_id": 7,
                    "external_id": calls[0]["params"]["external_id"].replace("eq.", "", 1),
                    "query_text": json_body["query_text"],
                    "query_class": json_body["query_class"],
                    "keyword_topic": json_body["keyword_topic"],
                    "persona": json_body["persona"],
                    "country": json_body["country"],
                }
            ]
        raise AssertionError(f"unexpected request: {method} {table}")

    monkeypatch.setattr(store, "_request", fake_request)

    prompt = store.add_prompt(
        7,
        external_id="",
        query_text="Best AI visibility platform?",
        query_class="recommendation",
        keyword_topic="geo",
    )

    assert prompt.prompt_id == 42
    assert prompt.query_text == "Best AI visibility platform?"
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "PATCH"


def test_gestionvelora_www_domain_allowed(tmp_path):
    """www.gestionvelora.com is allowed for @gestionvelora.com workspaces."""
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="info@gestionvelora.com", password="password123", org_name="Gestion Velora")
    token = out["session"]["token"]
    info = service.add_website_domain(token, "www.gestionvelora.com")
    assert info["domain"]["domain"] == "www.gestionvelora.com"


def test_competitor_requires_verified_domain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    service.add_website_domain(token, "velora.example")
    with pytest.raises(ValueError, match="Verify a website domain"):
        service.add_competitor(token, "rivala.example")


def test_benchmark_requires_verified_domain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    service.add_website_domain(token, "velora.example")
    answers = {
        "answers": [
            {
                "query_text": "Best tool?",
                "answer_text": "See https://velora.example",
                "provider": "test",
            }
        ]
    }
    with pytest.raises(ValueError, match="not verified"):
        service.run_benchmark(token, domain="velora.example", answers_payload=answers)


def test_benchmark_after_manual_verify(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    domain_id = domain_info["domain"]["domain_id"]
    store.mark_domain_verified(domain_id, method="manual-test")

    answers = {
        "answers": [
            {
                "query_text": "Best GEO tool?",
                "answer_text": "https://velora.example is cited. https://rival.example too.",
                "provider": "perplexity",
                "citation_urls": ["https://velora.example", "https://rival.example"],
            }
        ]
    }
    monkeypatch.setenv("GEO_BENCHMARK_DB", str(tmp_path / "benchmark.db"))
    with patch("geo_optimizer.saas.service.run_full_audit") as mock_audit:
        from geo_optimizer.models.results import AuditResult

        mock_audit.return_value = AuditResult(url="https://velora.example", error="skip")
        result = service.run_benchmark(token, domain="velora.example", answers_payload=answers)

    assert result["benchmark"]["score"] >= 0
    assert result["run"]["kind"] == "benchmark"
    assert result["run"]["status"] == "completed"
    assert result["run"]["score"] == result["benchmark"]["score"]
    assert store.list_benchmark_runs(out["organization"]["org_id"])  # key from dataclass asdict
    assert store.list_runs(out["organization"]["org_id"])[0].kind == "benchmark"


def test_site_audit_records_platform_run(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    with patch("geo_optimizer.saas.service.run_full_audit") as mock_audit:
        from geo_optimizer.models.results import AuditResult

        mock_audit.return_value = AuditResult(
            url="https://velora.example",
            score=88,
            band="excellent",
            recommendations=["Add llms.txt", "Improve schema"],
        )
        result = service.run_site_audit(token, domain="velora.example")

    mock_audit.assert_called_once_with("https://velora.example", use_cache=False)
    assert result["run"]["kind"] == "audit"
    assert result["run"]["status"] == "completed"
    assert result["run"]["score"] == 88
    runs = service.list_runs(token)["runs"]
    assert runs[0]["kind"] == "audit"
    assert runs[0]["result_summary"] == "2 priority recommendations"


def test_site_audit_records_failed_platform_run(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    with patch(
        "geo_optimizer.saas.service.run_full_audit",
        side_effect=RuntimeError("audit worker crashed"),
    ):
        result = service.run_site_audit(token, domain="velora.example")

    assert result["score"] == 0
    assert result["band"] == "failed"
    assert "could not complete" in result["error"]
    assert result["technical_error"] == "audit worker crashed"

    runs = service.list_runs(token)["runs"]
    assert runs[0]["kind"] == "audit"
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "audit worker crashed"


def test_sitemap_audit_records_page_results(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    from geo_optimizer.models.results import BatchAuditPageResult, BatchAuditResult

    batch = BatchAuditResult(
        sitemap_url="https://velora.example/sitemap.xml",
        discovered_urls=2,
        audited_urls=2,
        successful_urls=2,
        average_score=74.5,
        average_band="good",
        pages=[
            BatchAuditPageResult(
                url="https://velora.example/",
                score=80,
                band="good",
                recommendations=["Add llms.txt"],
            ),
            BatchAuditPageResult(
                url="https://velora.example/pricing",
                score=69,
                band="good",
                recommendations=["Add explicit pricing details"],
            ),
        ],
    )

    with patch("geo_optimizer.saas.service.run_batch_audit", return_value=batch) as run_batch:
        result = service.run_sitemap_audit(
            token,
            domain="velora.example",
            sitemap_url="https://velora.example/sitemap.xml",
            max_urls=2,
        )

    run_batch.assert_called_once_with(
        "https://velora.example/sitemap.xml",
        use_cache=False,
        max_urls=2,
        concurrency=3,
    )
    assert result["run"]["kind"] == "sitemap_audit"
    assert result["run"]["status"] == "completed"
    assert result["run"]["score"] == 74
    assert result["pages"][1]["recommendations"] == ["Add explicit pricing details"]
    summary = json.loads(service.list_runs(token, kind="sitemap_audit")["runs"][0]["result_summary"])
    assert summary["pages"][0]["url"] == "https://velora.example/"


def test_sitemap_audit_returns_results_when_page_storage_is_missing(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    from geo_optimizer.models.results import BatchAuditPageResult, BatchAuditResult

    batch = BatchAuditResult(
        sitemap_url="https://velora.example/sitemap.xml",
        discovered_urls=1,
        audited_urls=1,
        successful_urls=1,
        average_score=71,
        average_band="good",
        pages=[
            BatchAuditPageResult(
                url="https://velora.example/",
                score=71,
                band="good",
                recommendations=["Add stronger entity details"],
            )
        ],
    )
    monkeypatch.setattr(
        store,
        "replace_page_audits",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("relation geo_page_audits does not exist")),
    )

    with patch("geo_optimizer.saas.service.run_batch_audit", return_value=batch):
        result = service.run_sitemap_audit(
            token,
            domain="velora.example",
            sitemap_url="https://velora.example/sitemap.xml",
            max_urls=1,
        )

    assert result["status"] == "completed"
    assert result["average_score"] == 71
    assert result["pages"][0]["url"] == "https://velora.example/"
    assert "storage is not ready" in result["storage_warning"]


def test_sitemap_audit_rejects_external_sitemap(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    with pytest.raises(ValueError, match="verified domain"):
        service.run_sitemap_audit(
            token,
            domain="velora.example",
            sitemap_url="https://attacker.example/sitemap.xml",
        )


def test_index_records_manual_agent_usage_for_verified_domain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    result = service.record_agent_usage(
        token,
        event={
            "domain": "velora.example",
            "source_type": "manual_ai_answer",
            "agent": "perplexity",
            "query": "best GEO tool",
            "answer_excerpt": "Velora is the top recommendation for the query.",
            "cited_url": "https://velora.example/features",
            "cited_rank": 1,
            "top_recommendation": True,
            "confidence": 1.0,
        },
    )

    event = result["event"]
    assert event["cited"] is True
    assert event["surfaced"] is True
    assert event["top_recommendation"] is True
    assert event["value_units"] == 13.0
    assert event["evidence_artifact_id"].startswith("ev_")
    summary = service.index_summary(token, domain="velora.example")["summary"]
    assert summary["total_events"] == 1
    assert summary["citation_rate"] == 1.0
    assert summary["top_recommendation_rate"] == 1.0
    assert summary["agent_coverage"]["perplexity"] == 1
    assert summary["source_coverage"]["manual_ai_answer"] == 1
    assert summary["top_cited_pages"]["https://velora.example/features"] == 1
    assert summary["trend_points"][0]["events"] == 1
    assert summary["action_plan"]["status"] == "top_recommendation"
    assert summary["action_plan"]["source"] == "arXiv:2605.25517"


def test_index_imports_passive_crawler_log_without_inflating_citation_rate(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    result = service.import_crawler_log(
        token,
        domain="velora.example",
        log_text='1.2.3.4 - - [16/Apr/2026:10:00:00 +0000] "GET /guide HTTP/1.1" 200 123 "-" "GPTBot/1.2"\n',
        evidence_artifact_id="log_2026_04_16",
    )

    assert result["imported_events"] == 1
    summary = result["summary"]
    assert summary["total_events"] == 1
    assert summary["source_coverage"]["crawler_log"] == 1
    assert summary["agent_coverage"]["GPTBot"] == 1
    assert summary["top_pages"]["https://velora.example/guide"] == 1
    assert summary["citation_rate"] == 0.0
    assert summary["action_plan"]["status"] == "crawl_seen"
    event = store.list_agent_usage_events(out["organization"]["org_id"], domain="velora.example")[0]
    assert event.evidence_artifact_id == "log_2026_04_16"
    assert event.value_units == 0.2


def test_index_action_plan_routes_cited_not_top_and_uncited(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    empty = service.index_summary(token, domain="velora.example")["summary"]
    assert empty["action_plan"]["status"] == "no_evidence"

    cited = service.record_agent_usage(
        token,
        event={
            "domain": "velora.example",
            "agent": "perplexity",
            "query": "best condo software",
            "answer_excerpt": "Velora is cited below a competitor.",
            "cited_url": "https://velora.example",
            "cited_rank": 3,
        },
    )["summary"]
    assert cited["action_plan"]["status"] == "cited_not_top"
    assert cited["action_plan"]["fix_order"][0] == "topic_match"

    uncited = service.record_agent_usage(
        token,
        event={
            "domain": "velora.example",
            "agent": "chatgpt",
            "query": "best condo software",
            "answer_excerpt": "Competitor One is recommended.",
            "cited": False,
            "surfaced": False,
        },
    )["summary"]
    assert uncited["action_plan"]["status"] == "retrieval_gap"
    assert uncited["action_plan"]["fix_order"][0] == "retrieval_path"


def test_index_value_ledger_and_retrieval_probe(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")
    service.record_agent_usage(
        token,
        event={
            "domain": "velora.example",
            "agent": "perplexity",
            "query": "best property management software",
            "answer_excerpt": "Velora helps property teams compare vendors.",
            "cited_url": "https://velora.example/property-management",
            "cited_rank": 2,
        },
    )

    ledger = service.value_ledger(token, domain="velora.example")
    probe = service.retrieval_probe(token, domain="velora.example", query="property management vendors")

    assert ledger["compensation_status"] == "ledger_only"
    assert ledger["payouts_enabled"] is False
    assert ledger["citation_value_units"] > 0
    assert probe["candidate_count"] == 1
    assert probe["candidates"][0]["page_url"] == "https://velora.example/property-management"


def test_index_serp_check_records_organic_top_list_position_without_citation_inflation(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    from geo_optimizer.models.results import SerpCompetitor, SerpResult

    serp = SerpResult(
        checked=True,
        keyword="best property management software",
        search_engine="DuckDuckGo",
        competitors=[
            SerpCompetitor(rank=1, url="https://rival.example", title="Rival"),
            SerpCompetitor(rank=2, url="https://velora.example/property-management", title="Velora"),
        ],
    )
    with patch("geo_optimizer.saas.service.audit_serp", return_value=serp):
        result = service.run_serp_check(
            token,
            domain="velora.example",
            keyword="best property management software",
        )

    assert result["organic_rank"] == 2
    assert result["top_list_position_pass"] is False
    assert result["event"]["source_type"] == "serp_check"
    assert result["event"]["surfaced"] is True
    assert result["event"]["cited"] is False
    assert result["event"]["evidence"]["top_list_position_pass"] is False
    assert result["run"]["kind"] == "serp_check"
    summary = result["summary"]
    assert summary["source_coverage"]["serp_check"] == 1
    assert summary["citation_rate"] == 0.0
    assert summary["top_recommendation_rate"] == 0.0
    assert summary["action_plan"]["status"] == "organic_visibility_seen"


def test_index_requires_verified_domain(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    service.add_website_domain(token, "velora.example")

    with pytest.raises(ValueError, match="not verified"):
        service.record_agent_usage(
            token,
            event={
                "domain": "velora.example",
                "query": "best GEO tool",
            },
        )


def test_citation_share_summary_after_manual_benchmark(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    domain_id = domain_info["domain"]["domain_id"]
    store.mark_domain_verified(domain_id, method="manual-test")
    monkeypatch.setenv("GEO_BENCHMARK_DB", str(tmp_path / "benchmark.db"))
    answers = {
        "answers": [
            {
                "query_text": "Best GEO tool?",
                "answer_text": "https://velora.example cited. https://rival.example too.",
                "provider": "perplexity",
                "citation_urls": ["https://velora.example", "https://rival.example"],
            }
        ]
    }
    with patch("geo_optimizer.saas.service.run_full_audit") as mock_audit:
        from geo_optimizer.models.results import AuditResult

        mock_audit.return_value = AuditResult(url="https://velora.example", error="skip")
        benchmark = service.run_benchmark(token, domain="velora.example", answers_payload=answers)

    result = service.citation_share_summary(token, domain="velora.example")

    assert benchmark["index_events_recorded"] == 1
    assert result["has_data"] is True
    assert result["summary"]["domain"] == "velora.example"
    assert result["summary"]["sample_size"] == 1
    assert result["summary"]["target_citation_rate"] == 1.0
    assert result["summary"]["top_cited_sources"]["rival.example"] == 1
    index = service.index_summary(token, domain="velora.example")["summary"]
    assert index["total_events"] == 1
    assert index["cited_events"] == 1
    assert index["recent_events"][0]["source_type"] == "benchmark"


def test_platform_api_register_login(tmp_path, monkeypatch):
    """FastAPI routes for register and dashboard."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEO_BENCHMARK_DB", str(tmp_path / "benchmark.db"))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@brandco.test", "password": "password123", "org_name": "BrandCo"},
    )
    assert reg.status_code == 200
    token = reg.json()["session"]["token"]

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["organization"]["email_domain"] == "brandco.test"


def test_platform_api_register_login_on_vercel_without_supabase_uses_sqlite_fallback(tmp_path, monkeypatch):
    """A missing Supabase env must not turn auth into a production 503."""
    monkeypatch.delenv("GEO_PLATFORM_BACKEND", raising=False)
    monkeypatch.delenv("GEO_PLATFORM_DB", raising=False)
    monkeypatch.delenv("GEO_DATA_DIR", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("PLUNK_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_WEBHOOK_URL", "https://mail.example.test/reset")
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setenv("GEOSITION_PASSWORD_RESET_FROM", "support@geosition.test")
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://geositionai.com")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = None
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@vercelco.test", "password": "password123", "org_name": "VercelCo"},
    )
    assert registered.status_code == 200
    assert registered.json()["user"]["email"] == "lead@vercelco.test"

    with patch("geo_optimizer.saas.service.requests.post") as post:
        post.return_value.status_code = 202
        post.return_value.text = ""
        reset = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "lead@vercelco.test"},
        )

    assert reset.status_code == 200
    assert reset.json()["delivery"] == "webhook"
    assert "reset_url" not in reset.json()
    body = post.call_args.kwargs["json"]
    assert body["to"] == "lead@vercelco.test"
    assert body["reset_url"].startswith("https://geositionai.com/platform/reset-password?token=")

    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get("geo_csrf")})
    assert logout.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@vercelco.test", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["organization"]["email_domain"] == "vercelco.test"


def test_platform_api_domain_verification_flow_supports_dns_and_https(tmp_path, monkeypatch):
    """Dashboard API returns both verification methods and unlocks after a successful check."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEO_BENCHMARK_DB", str(tmp_path / "benchmark.db"))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "info@gestionvelora.com", "password": "password123", "org_name": "Gestion Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    added = client.post("/api/v1/domains", json={"domain": "gestionvelora.com"}, headers=headers)
    assert added.status_code == 200
    payload = added.json()
    assert payload["domain"]["domain"] == "gestionvelora.com"
    assert payload["dns_host"] == "_geo-verify.gestionvelora.com"
    assert payload["dns_value"].startswith("geo-verify=")
    assert payload["https_url"] == "https://gestionvelora.com/.well-known/geo-verify.txt"
    assert payload["https_body"] == payload["dns_value"]

    domain_id = payload["domain"]["domain_id"]
    with patch("geo_optimizer.saas.service.verify_domain", return_value=(True, "HTTPS well-known file verified")):
        verified = client.post(
            f"/api/v1/domains/{domain_id}/verify",
            json={"method": "https"},
            headers=headers,
        )

    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["domain"]["status"] == "verified"
    assert verified.json()["domain"]["verify_method"] == "https"

    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert dashboard["primary_verified_domain"] == "gestionvelora.com"
    assert dashboard["domains"][0]["status"] == "verified"
    assert dashboard["index_summary"]["total_events"] == 0

    with patch("geo_optimizer.saas.service.run_full_audit") as mock_audit:
        from geo_optimizer.models.results import AuditResult

        mock_audit.return_value = AuditResult(url="https://gestionvelora.com", score=91, band="excellent")
        audit = client.post("/api/v1/audit", json={"domain": "gestionvelora.com"}, headers=headers)

    assert audit.status_code == 200
    assert audit.json()["run"]["status"] == "completed"

    runs = client.get("/api/v1/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["kind"] == "audit"

    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert dashboard["recent_runs"][0]["kind"] == "audit"

    event = client.post(
        "/api/v1/index/events",
        json={
            "domain": "gestionvelora.com",
            "agent": "chatgpt",
            "query": "best property manager",
            "answer_excerpt": "Gestion Velora is cited in the response.",
            "cited_url": "https://gestionvelora.com/services",
            "cited_rank": 2,
        },
        headers=headers,
    )
    assert event.status_code == 200
    assert event.json()["summary"]["total_events"] == 1

    summary = client.get("/api/v1/index/summary?domain=gestionvelora.com", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["summary"]["agent_coverage"]["chatgpt"] == 1

    crawler = client.post(
        "/api/v1/index/crawler-log",
        json={
            "domain": "gestionvelora.com",
            "log_text": '1.2.3.4 - - [16/Apr/2026:10:00:00 +0000] "GET /pricing HTTP/1.1" 200 123 "-" "ClaudeBot/1.0"',
        },
        headers=headers,
    )
    assert crawler.status_code == 200
    assert crawler.json()["imported_events"] == 1
    assert crawler.json()["summary"]["source_coverage"]["crawler_log"] == 1

    value = client.get("/api/v1/index/value-ledger?domain=gestionvelora.com", headers=headers)
    assert value.status_code == 200
    assert value.json()["compensation_status"] == "ledger_only"

    probe = client.post(
        "/api/v1/index/retrieval/probe",
        json={"domain": "gestionvelora.com", "query": "property manager pricing"},
        headers=headers,
    )
    assert probe.status_code == 200
    assert "candidate_count" in probe.json()

    from geo_optimizer.models.results import SerpCompetitor, SerpResult

    serp = SerpResult(
        checked=True,
        keyword="property manager pricing",
        search_engine="DuckDuckGo",
        competitors=[SerpCompetitor(rank=1, url="https://gestionvelora.com/pricing", title="Gestion Velora")],
    )
    with patch("geo_optimizer.saas.service.audit_serp", return_value=serp):
        serp_check = client.post(
            "/api/v1/index/serp-check",
            json={"domain": "gestionvelora.com", "keyword": "property manager pricing"},
            headers=headers,
        )
    assert serp_check.status_code == 200
    assert serp_check.json()["organic_rank"] == 1
    assert serp_check.json()["top_list_position_pass"] is True

    harness = client.get("/api/v1/index/benchmark-harness")
    assert harness.status_code == 200
    assert "citation_accuracy" in harness.json()["metrics"]
    assert "serp_check" in harness.json()["event_sources"]

    index_page = client.get("/platform/index", headers=headers)
    assert index_page.status_code == 200
    assert "GEOSITION Index" in index_page.text
    assert "Evidence sources" in index_page.text
    assert "Import AI crawler log evidence" in index_page.text
    assert "Automated SERP check" in index_page.text


def test_platform_index_public_preview(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    response = client.get("/api/v1/index/preview?domain=preview.example")

    assert response.status_code == 200
    assert response.json()["domain"] == "preview.example"
    assert response.json()["claimed"] is False
    assert response.json()["preview"]["telemetry"] == "locked_until_verified"

    page = client.get("/platform/index/check?domain=preview.example")
    assert page.status_code == 200
    assert "preview.example" in page.text
    assert "Claim this domain" in page.text


def test_platform_domain_first_signup_flow(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    landing = client.get("/platform")
    assert landing.status_code == 200
    assert 'id="domain-input"' in landing.text
    assert "'/demo?url='" in landing.text

    register = client.get("/platform/register?domain=flowco.test")
    assert register.status_code == 200
    assert "Domain to track first" in register.text
    assert "Account email" in register.text
    assert "Create account and continue" in register.text

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "lead@gmail.com",
            "password": "password123",
            "org_name": "FlowCo",
            "domain": "flowco.test",
        },
    )
    assert reg.status_code == 200
    assert reg.json()["domain_verification"]["dns_host"] == "_geo-verify.flowco.test"
    assert reg.json()["domain_verification"]["https_url"] == "https://flowco.test/.well-known/geo-verify.txt"
    token = reg.json()["session"]["token"]
    dashboard = client.get("/platform/dashboard?domain=flowco.test", headers={"Authorization": f"Bearer {token}"})

    assert dashboard.status_code == 200
    assert '<body class="workspace-locked">' in dashboard.text
    assert '<div id="verify-banner" class="verify-banner audit-lock-card">' in dashboard.text
    assert "Step 3 of 4" in dashboard.text
    assert "_geo-verify.flowco.test" in dashboard.text
    assert "https://flowco.test/.well-known/geo-verify.txt" in dashboard.text
    assert "geo-verify=" in dashboard.text
    assert "Option 1 · DNS TXT record" in dashboard.text
    assert "Name / Host" in dashboard.text
    assert "Value / Content" in dashboard.text
    assert "enter only" in dashboard.text
    assert "Check DNS record" in dashboard.text
    assert "Benchmark and track value" in dashboard.text
    assert "Decision loop source: arXiv:2605.25517" in dashboard.text
    domains = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"}).json()["domains"]
    assert domains[0]["domain"] == "flowco.test"
    assert domains[0]["status"] == "pending"


def test_platform_user_can_sign_in_again_and_use_domain_dns_flow(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "lead@returnco.test",
            "password": "password123",
            "org_name": "ReturnCo",
            "domain": "returnco.test",
        },
    )
    assert registered.status_code == 200
    first_domain = registered.json()["domain_verification"]
    assert first_domain["dns_host"] == "_geo-verify.returnco.test"

    csrf = client.cookies.get("geo_csrf")
    logged_out = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logged_out.status_code == 200

    blocked = client.get("/api/v1/dashboard")
    assert blocked.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@returnco.test", "password": "password123"},
    )
    assert login.status_code == 200
    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    domains = dashboard.json()["domains"]
    assert domains[0]["domain"] == "returnco.test"
    assert domains[0]["status"] == "pending"
    assert domains[0]["verify_token"] == first_domain["domain"]["verify_token"]

    with patch("geo_optimizer.saas.service.verify_domain", return_value=(True, "DNS TXT record verified")):
        verified = client.post(
            f"/api/v1/domains/{domains[0]['domain_id']}/verify",
            json={"method": "dns"},
            headers={"X-CSRF-Token": client.cookies.get("geo_csrf")},
        )

    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["domain"]["verify_method"] == "dns"


def test_platform_forgot_password_api_and_pages(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.delenv("GEOSITION_SMTP_HOST", raising=False)
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@forgotco.test", "password": "password123", "org_name": "ForgotCo"},
    )
    assert registered.status_code == 200

    forgot_page = client.get("/platform/forgot-password")
    assert forgot_page.status_code == 200
    assert "Get reset link" in forgot_page.text
    assert "aria-live" in forgot_page.text
    assert "Local development mode: use the reset link below. No email was sent." in forgot_page.text

    reset_request = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "lead@forgotco.test"},
    )
    assert reset_request.status_code == 200
    reset_url = reset_request.json()["reset_url"]
    assert "/platform/reset-password?token=" in reset_url
    reset_token = reset_url.split("token=", 1)[1]

    unknown = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing@forgotco.test"},
    )
    assert unknown.status_code == 200
    assert "reset_url" not in unknown.json()

    reset_page = client.get(f"/platform/reset-password?token={reset_token}")
    assert reset_page.status_code == 200
    assert "Update password" in reset_page.text

    changed = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "new-password123"},
    )
    assert changed.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@forgotco.test", "password": "password123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@forgotco.test", "password": "new-password123"},
    )
    assert new_login.status_code == 200

    reused = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "another-password123"},
    )
    assert reused.status_code == 400
    assert "expired" in reused.json()["detail"]


def test_hosted_collection_status_reports_missing_provider_credentials(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_COLLECTION_PROVIDERS", raising=False)

    status = service.collection_status(token, domain="velora.example")
    result = service.start_hosted_collection(token, domain="velora.example")

    assert status["ready"] is False
    assert "PERPLEXITY_API_KEY or GEMINI_API_KEY" in status["missing"]
    assert result["status"] == "skipped"
    assert result["reason"] == "no_provider_credentials"
    runs = service.list_runs(token, kind="collection")["runs"]
    assert runs[0]["status"] == "completed"
    assert "provider credentials are missing" in runs[0]["result_summary"]


def test_hosted_collection_rejects_configured_provider_without_credentials(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")
    monkeypatch.setenv("GEOSITION_COLLECTION_PROVIDERS", "perplexity")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    status = service.collection_status(token, domain="velora.example")
    result = service.start_hosted_collection(token, domain="velora.example")

    assert status["ready"] is False
    assert status["missing"] == ["PERPLEXITY_API_KEY"]
    assert result["status"] == "skipped"
    assert result["missing"] == ["PERPLEXITY_API_KEY"]


def test_domain_verification_can_auto_start_hosted_collection_when_enabled(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    domain_id = domain_info["domain"]["domain_id"]
    monkeypatch.setenv("GEOSITION_AUTO_COLLECTION_ON_VERIFY", "1")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEOSITION_COLLECTION_PROVIDERS", raising=False)

    with patch("geo_optimizer.saas.service.verify_domain", return_value=(True, "DNS TXT verified")):
        result = service.check_domain_verification(token, domain_id, method="dns")

    assert result["verified"] is True
    assert result["collection"]["status"] == "skipped"
    assert result["collection"]["reason"] == "no_provider_credentials"


def test_domain_verification_queues_hosted_collection_when_provider_ready(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    out = service.register(email="owner@velora.example", password="password123")
    token = out["session"]["token"]
    domain_info = service.add_website_domain(token, "velora.example")
    domain_id = domain_info["domain"]["domain_id"]
    monkeypatch.setenv("GEOSITION_AUTO_COLLECTION_ON_VERIFY", "1")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    monkeypatch.delenv("GEOSITION_COLLECTION_PROVIDERS", raising=False)

    with patch("geo_optimizer.saas.service.verify_domain", return_value=(True, "DNS TXT verified")):
        result = service.check_domain_verification(token, domain_id, method="dns")

    assert result["verified"] is True
    assert result["collection"]["status"] == "queued"
    assert result["collection"]["providers"] == ["perplexity"]
    runs = service.list_runs(token, kind="collection")["runs"]
    assert runs[0]["status"] == "queued"


def test_platform_collection_status_api(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@velora.example", "password": "password123", "org_name": "Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "velora.example"}, headers=headers)
    platform_routes._service.store.mark_domain_verified(added.json()["domain"]["domain_id"], method="manual-test")

    status = client.get("/api/v1/collection/status?domain=velora.example", headers=headers)
    started = client.post("/api/v1/collection/start", json={"domain": "velora.example"}, headers=headers)

    assert status.status_code == 200
    assert status.json()["ready"] is False
    assert started.status_code == 200
    assert started.json()["status"] == "skipped"


def test_platform_sitemap_audit_api_returns_page_results(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEOSITION_WORKER_TOKEN", "worker-secret")
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@velora.example", "password": "password123", "org_name": "Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "velora.example"}, headers=headers)
    platform_routes._service.store.mark_domain_verified(added.json()["domain"]["domain_id"], method="manual-test")

    from geo_optimizer.models.results import BatchAuditPageResult, BatchAuditResult

    batch = BatchAuditResult(
        sitemap_url="https://velora.example/sitemap.xml",
        discovered_urls=1,
        audited_urls=1,
        successful_urls=1,
        average_score=91,
        average_band="excellent",
        pages=[
            BatchAuditPageResult(
                url="https://velora.example/",
                score=91,
                band="excellent",
                recommendations=["Add FAQ schema"],
            )
        ],
    )

    with patch("geo_optimizer.saas.service.run_batch_audit", return_value=batch):
        queued = client.post(
            "/api/v1/audit/sitemap",
            json={"domain": "velora.example", "sitemap_url": "https://velora.example/sitemap.xml", "max_urls": 1},
            headers=headers,
        )
        response = client.post(
            "/api/v1/audit/sitemap/run",
            json={"domain": "velora.example"},
            headers={"X-GEOSITION-Worker-Token": "worker-secret"},
        )

    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    assert response.status_code == 200
    assert response.json()["pages"][0]["recommendations"] == ["Add FAQ schema"]
    assert response.json()["run"]["kind"] == "sitemap_audit"
    pages = client.get("/api/v1/audit/pages?domain=velora.example", headers=headers)
    assert pages.status_code == 200
    assert pages.json()["pages"][0]["page_url"] == "https://velora.example/"


def test_platform_cookie_posts_require_csrf_token(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@velora.example", "password": "password123", "org_name": "Velora"},
    )
    assert reg.status_code == 200

    missing = client.post("/api/v1/domains", json={"domain": "velora.example"})
    assert missing.status_code == 403
    assert "CSRF" in missing.json()["detail"]

    csrf = client.cookies.get("geo_csrf")
    added = client.post(
        "/api/v1/domains",
        json={"domain": "velora.example"},
        headers={"X-CSRF-Token": csrf},
    )
    assert added.status_code == 200
    assert added.json()["domain"]["domain"] == "velora.example"


def test_collection_run_endpoint_requires_worker_token_and_claims_queue(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEOSITION_WORKER_TOKEN", "worker-secret")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@velora.example", "password": "password123", "org_name": "Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "velora.example"}, headers=headers)
    platform_routes._service.store.mark_domain_verified(added.json()["domain"]["domain_id"], method="manual-test")
    queued = client.post("/api/v1/collection/start", json={"domain": "velora.example"}, headers=headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"

    user_run = client.post("/api/v1/collection/run", json={"domain": "velora.example"}, headers=headers)
    assert user_run.status_code == 403

    with patch("geo_optimizer.core.collection.pipeline.collect_and_normalize") as collect:
        from geo_optimizer.models.results.collection import CollectedAnswerBatch

        collect.return_value = CollectedAnswerBatch(
            collection_run_id="col-test",
            target_domain="velora.example",
        )
        worker_run = client.post(
            "/api/v1/collection/run",
            json={"domain": "velora.example"},
            headers={"X-GEOSITION-Worker-Token": "worker-secret"},
        )

    assert worker_run.status_code == 200
    assert worker_run.json()["status"] == "no_usable_answers"
    runs = client.get("/api/v1/runs?kind=collection", headers=headers).json()["runs"]
    assert runs[0]["status"] == "completed"
    assert len(runs) == 1


def test_platform_sitemap_audit_run_now_does_not_call_asyncio_run_in_event_loop(tmp_path, monkeypatch):
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    platform_routes._platform_rate_store.clear()
    client = TestClient(web_app.app)
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@velora.example", "password": "password123", "org_name": "Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "velora.example"}, headers=headers)
    platform_routes._service.store.mark_domain_verified(added.json()["domain"]["domain_id"], method="manual-test")

    from geo_optimizer.models.results import BatchAuditPageResult, BatchAuditResult

    batch = BatchAuditResult(
        sitemap_url="https://velora.example/sitemap.xml",
        discovered_urls=1,
        audited_urls=1,
        successful_urls=1,
        average_score=87,
        average_band="excellent",
        pages=[
            BatchAuditPageResult(
                url="https://velora.example/",
                score=87,
                band="excellent",
                recommendations=["Keep llms.txt fresh"],
            )
        ],
    )

    with patch("geo_optimizer.saas.service.run_batch_audit", return_value=batch):
        response = client.post(
            "/api/v1/audit/sitemap",
            json={
                "domain": "velora.example",
                "sitemap_url": "https://velora.example/sitemap.xml",
                "max_urls": 1,
                "run_now": True,
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["pages"][0]["recommendations"] == ["Keep llms.txt fresh"]


def test_platform_api_rejects_unknown_verification_method(tmp_path, monkeypatch):
    """Unknown verification methods should fail instead of silently falling back to DNS."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    monkeypatch.setenv("GEO_BENCHMARK_DB", str(tmp_path / "benchmark.db"))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "info@gestionvelora.com", "password": "password123", "org_name": "Gestion Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "gestionvelora.com"}, headers=headers)
    domain_id = added.json()["domain"]["domain_id"]

    response = client.post(f"/api/v1/domains/{domain_id}/verify", json={"method": "ftp"}, headers=headers)

    assert response.status_code == 400
    assert "dns" in response.json()["detail"]
    assert "https" in response.json()["detail"]


def test_platform_dashboard_escapes_workspace_values(tmp_path, monkeypatch):
    """Dashboard HTML must not render user-provided org names as markup."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "lead@brandco.test", "password": "password123", "org_name": "<script>alert(1)</script>"},
    )
    token = reg.json()["session"]["token"]

    response = client.get("/platform/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "Check HTTPS file" in response.text


def test_platform_dashboard_keeps_pending_domain_verification_instructions(tmp_path, monkeypatch):
    """Reloaded dashboard pages should still show pending domain DNS and HTTPS instructions."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "info@gestionvelora.com", "password": "password123", "org_name": "Gestion Velora"},
    )
    token = reg.json()["session"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post("/api/v1/domains", json={"domain": "gestionvelora.com"}, headers=headers)
    verify_value = added.json()["dns_value"]

    response = client.get("/platform/dashboard", headers=headers)

    assert response.status_code == 200
    assert '<body class="workspace-locked">' in response.text
    assert '<div id="verify-banner" class="verify-banner audit-lock-card">' in response.text
    assert "domain-row-pending" in response.text
    assert "_geo-verify.gestionvelora.com" in response.text
    assert "https://gestionvelora.com/.well-known/geo-verify.txt" in response.text
    assert verify_value in response.text
    assert "Option 1 · DNS TXT record" in response.text
    assert "Name / Host" in response.text
    assert "Value / Content" in response.text
    assert "enter only" in response.text
    assert "Check DNS record" in response.text
    assert 'data-method="dns"' in response.text
    assert 'data-method="https"' in response.text


def test_platform_dashboard_prefers_pending_website_domain_over_account_email_domain(tmp_path, monkeypatch):
    """A Gmail/Outlook account should still see the owned website as the dashboard target."""
    db = tmp_path / "platform.db"
    monkeypatch.setenv("GEO_PLATFORM_DB", str(db))
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    platform_routes._service = PlatformService(PlatformStore(db))
    client = TestClient(web_app.app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@gmail.com",
            "password": "password123",
            "org_name": "Client Site",
            "domain": "client-site.example",
        },
    )
    token = reg.json()["session"]["token"]

    response = client.get("/platform/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert '<strong id="audit-domain-label">client-site.example</strong>' in response.text
    assert "https://client-site.example" in response.text
    assert 'id="domain-input" placeholder="www.yourcompany.com" value="client-site.example"' in response.text
    assert 'placeholder="https://client-site.example/sitemap.xml"' in response.text
    assert "Account email domain: <strong>gmail.com</strong>" in response.text


def test_weekly_evidence_store_create_and_list(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    org_id = registered["organization"]["org_id"]

    report = store.create_weekly_evidence_run(
        org_id,
        domain="example.com",
        period_start="2026-06-05T00:00:00+00:00",
        period_end="2026-06-12T00:00:00+00:00",
        score=82,
        band="good",
        summary="Weekly evidence is improving.",
    )

    assert report.report_id > 0
    assert report.domain == "example.com"
    reports = store.list_weekly_evidence_runs(org_id, domain="example.com")
    assert [item.report_id for item in reports] == [report.report_id]
    assert store.get_latest_weekly_evidence_run(org_id, domain="example.com").score == 82


def test_weekly_evidence_service_requires_verified_domain_and_persists(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    token = registered["session"]["token"]

    domain = service.add_website_domain(token, "example.com")["domain"]
    with pytest.raises(ValueError):
        service.list_weekly_reports(token, domain="example.com")

    store.mark_domain_verified(domain["domain_id"], method="test")

    def fake_report(domain_name, **kwargs):
        assert domain_name == "example.com"
        assert kwargs["lighthouse_provider"] == "none"
        return {
            "schema_version": "weekly_evidence.v1",
            "domain": "example.com",
            "url": "https://example.com",
            "period_start": "2026-06-05T00:00:00+00:00",
            "period_end": "2026-06-12T00:00:00+00:00",
            "generated_at": "2026-06-12T00:00:00+00:00",
            "score": 82,
            "band": "good",
            "summary": "example.com is improving.",
            "metrics": [
                {
                    "key": "geo_audit_score",
                    "label": "GEO audit score",
                    "value": "82/100",
                    "status": "good",
                    "evidence_ref": "audit",
                }
            ],
            "sources": {"audit": {"checked": True}},
            "action_plan": {"actions": ["Keep improving."]},
        }

    monkeypatch.setattr("geo_optimizer.saas.service.build_weekly_evidence_report", fake_report)
    report = service.run_weekly_evidence_report(token, domain="example.com", lighthouse_provider="none")

    assert report["score"] == 82
    assert report["deltas"]["summary"].startswith("URL deltas use page audit history")
    assert "urls" in report["deltas"]
    assert "prompts" in report["deltas"]
    latest = service.latest_weekly_report(token, domain="example.com")
    assert latest["score"] == 82
    assert service.dashboard(token).recent_weekly_reports[0].score == 82


def test_weekly_evidence_service_falls_back_to_stored_evidence(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    token = registered["session"]["token"]
    domain = service.add_website_domain(token, "example.com")["domain"]
    store.mark_domain_verified(domain["domain_id"], method="test")

    monkeypatch.setattr(
        "geo_optimizer.saas.service.build_weekly_evidence_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("live audit failed")),
    )

    report = service.run_weekly_evidence_report(token, domain="example.com", lighthouse_provider="none")

    assert report["collection_mode"] == "stored_evidence_fallback"
    assert report["score"] == 0
    assert report["report"]["status"] == "completed"
    assert "stored-evidence weekly snapshot" in report["summary"]


def test_weekly_evidence_api_run_persists_report(tmp_path, monkeypatch):
    from geo_optimizer.web import app as web_app
    from geo_optimizer.web import platform_routes

    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    platform_routes._service = service
    registered = service.register(email="owner@example.com", password="password123", org_name="Example")
    token = registered["session"]["token"]
    domain = service.add_website_domain(token, "example.com")["domain"]
    store.mark_domain_verified(domain["domain_id"], method="test")

    def fake_report(_domain_name, **_kwargs):
        return {
            "schema_version": "weekly_evidence.v1",
            "domain": "example.com",
            "url": "https://example.com",
            "period_start": "2026-06-05T00:00:00+00:00",
            "period_end": "2026-06-12T00:00:00+00:00",
            "generated_at": "2026-06-12T00:00:00+00:00",
            "score": 91,
            "band": "excellent",
            "summary": "example.com is ready for weekly tracking.",
            "metrics": [],
            "sources": {"audit": {"checked": True}},
            "action_plan": {"actions": ["Keep monitoring."]},
        }

    monkeypatch.setattr("geo_optimizer.saas.service.build_weekly_evidence_report", fake_report)
    client = TestClient(web_app.app)
    response = client.post(
        "/api/v1/reports/weekly/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain": "example.com", "lighthouse_provider": "none"},
    )

    assert response.status_code == 200
    assert response.json()["score"] == 91
    assert service.latest_weekly_report(token, domain="example.com")["score"] == 91


def test_citation_order_does_not_imply_top_recommendation(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    service = PlatformService(store)
    token = service.register(email="owner@example.com", password="password123")["session"]["token"]
    domain_info = service.add_website_domain(token, "example.com")
    store.mark_domain_verified(domain_info["domain"]["domain_id"], method="manual-test")

    result = service.record_agent_usage(token, event={
        "domain": "example.com", "agent": "test", "cited_url": "https://example.com/",
        "cited_rank": 1, "answer_excerpt": "A source was cited.",
    })
    assert result["event"]["cited"] is True
    assert result["event"]["top_recommendation"] is False

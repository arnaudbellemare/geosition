"""GEOSITION Platform API and HTML routes (/platform, /api/v1)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from geo_optimizer.saas.domain_verify import dns_verify_hostname, https_verify_url
from geo_optimizer.saas.models import IndexTrendPoint, PlatformRun
from geo_optimizer.saas.service import PlatformService

router = APIRouter(tags=["platform"])
_logger = logging.getLogger(__name__)
_TEMPLATES = Path(__file__).parent / "templates" / "platform"
_PLATFORM_ASSETS = _TEMPLATES / "assets"
_service: PlatformService | None = None
_CSRF_COOKIE = "geo_csrf"
_CSRF_HEADER = "x-csrf-token"
_PLATFORM_RATE_WINDOW = 60
_PLATFORM_RATE_LIMITS = {
    "auth": 12,
    "write": 60,
    "expensive": 30,
}
_platform_rate_store: dict[str, list[float]] = {}


def _get_service() -> PlatformService:
    global _service
    if _service is None:
        _service = PlatformService()
    return _service


def _platform_service_http_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    if "Vercel platform auth requires durable Supabase storage" in message:
        detail = (
            "Platform storage is not configured. Set SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in Vercel."
        )
    else:
        detail = "Platform storage is unavailable. Check the server database configuration and try again."
    return HTTPException(status_code=503, detail=detail)


def _platform_internal_error(message: str, exc: Exception) -> HTTPException:
    _logger.exception(message)
    return HTTPException(status_code=500, detail=f"{message}. Try again soon.")


# Larger body limit for answers upload (parent app middleware allows 4KB globally)
_PLATFORM_MAX_BODY = 2 * 1024 * 1024


class RegisterBody(BaseModel):
    email: str
    password: str = Field(min_length=8)
    org_name: str = ""
    domain: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    token: str
    password: str = Field(min_length=8)


class DomainBody(BaseModel):
    domain: str


class SitemapAuditBody(BaseModel):
    domain: str
    sitemap_url: str = ""
    max_urls: int = Field(default=10, ge=1, le=25)
    run_now: bool = False


class PageAuditHistoryBody(BaseModel):
    page_url: str
    limit: int = Field(default=12, ge=1, le=50)


class VerifyBody(BaseModel):
    method: str = "dns"


class CompetitorBody(BaseModel):
    domain: str


class PromptBody(BaseModel):
    query_text: str
    external_id: str = ""
    query_class: str = ""
    keyword_topic: str = ""


class IndexEventBody(BaseModel):
    domain: str
    source_type: str = "ai_answer"
    agent: str = ""
    query: str = ""
    answer_excerpt: str = ""
    page_url: str = ""
    cited_url: str = ""
    cited_rank: Optional[int] = None  # noqa: UP045 - Pydantic evaluates request models on Python 3.9.
    surfaced: Optional[bool] = None  # noqa: UP045
    cited: Optional[bool] = None  # noqa: UP045
    top_recommendation: Optional[bool] = None  # noqa: UP045
    confidence: float = 1.0
    evidence_artifact_id: str = ""
    evidence: dict[str, object] = Field(default_factory=dict)


class IndexCrawlerLogBody(BaseModel):
    domain: str
    log_text: str
    evidence_artifact_id: str = ""


class RetrievalProbeBody(BaseModel):
    domain: str
    query: str


class SerpCheckBody(BaseModel):
    domain: str
    keyword: str


class WeeklyReportBody(BaseModel):
    domain: str
    answers: Optional[object] = None  # noqa: UP045 - Pydantic evaluates request models on Python 3.9.
    lighthouse_provider: str = "none"


class HostedCollectionBody(BaseModel):
    domain: str
    providers: list[str] = Field(default_factory=list)


class SearchMeasurementBody(BaseModel):
    domain: str = Field(max_length=253)
    provider: str = Field(max_length=16)
    property_id: str = Field(max_length=2048)
    access_token: str = Field(max_length=8192, repr=False)
    start_date: str = Field(max_length=10)
    end_date: str = Field(max_length=10)


class SearchConnectionBody(BaseModel):
    domain: str = Field(max_length=253)
    provider: str = Field(max_length=16)


def _read_template(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def _nonce_attr(request: Request) -> str:
    """Build the `nonce="..."` attribute for inline <script> tags (CSP fix #75)."""
    nonce = getattr(request.state, "csp_nonce", "")
    return f' nonce="{nonce}"' if nonce else ""


def _render_template(request: Request, name: str) -> str:
    """Read a template and inject the CSP nonce into `__NONCE_ATTR__` placeholders."""
    return _read_template(name).replace("__NONCE_ATTR__", _nonce_attr(request))


def _cacheable_response(content: bytes | str, media_type: str, *, max_age: int = 31_536_000) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": f"public, max-age={max_age}, immutable"},
    )


def _csrf_token(request: Request) -> str:
    token = request.cookies.get(_CSRF_COOKIE, "")
    return token if token else secrets.token_urlsafe(24)


def _attach_csrf_cookie(response: Response, request: Request) -> Response:
    response.set_cookie(
        _CSRF_COOKIE,
        _csrf_token(request),
        httponly=False,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    return response


def _set_session_cookies(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        "geo_session",
        token,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    _attach_csrf_cookie(response, request)


def _uses_cookie_auth(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    return not auth.startswith("Bearer ") and bool(request.cookies.get("geo_session"))


def _validate_csrf(request: Request) -> None:
    if not _uses_cookie_auth(request):
        return
    cookie = request.cookies.get(_CSRF_COOKIE, "")
    header = request.headers.get(_CSRF_HEADER, "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")


def _platform_rate_key(request: Request, bucket: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{bucket}:{client}"


def _enforce_platform_rate_limit(request: Request, bucket: str = "write") -> None:
    limit = _PLATFORM_RATE_LIMITS.get(bucket, _PLATFORM_RATE_LIMITS["write"])
    now = time.time()
    key = _platform_rate_key(request, bucket)
    timestamps = [ts for ts in _platform_rate_store.get(key, []) if now - ts < _PLATFORM_RATE_WINDOW]
    if len(timestamps) >= limit:
        _platform_rate_store[key] = timestamps
        raise HTTPException(status_code=429, detail="Too many platform requests. Try again soon.")
    timestamps.append(now)
    _platform_rate_store[key] = timestamps
    if len(_platform_rate_store) > 10_000:
        oldest = sorted(
            _platform_rate_store, key=lambda item: _platform_rate_store[item][-1] if _platform_rate_store[item] else 0
        )
        for stale in oldest[:100]:
            _platform_rate_store.pop(stale, None)


def _html(value: object) -> str:
    """Escape user-controlled values before injecting them into server templates."""
    return escape(str(value), quote=True)


def _domain_list_item(domain) -> str:
    """Render a dashboard domain row with verification instructions when pending."""
    domain_name = _html(domain.domain)
    status = _html(domain.status)
    if domain.status == "verified":
        return f'<li class="domain-row"><strong>{domain_name}</strong> · verified</li>'

    dns_host = _html(dns_verify_hostname(domain.domain))
    verify_value = _html(f"geo-verify={domain.verify_token}")
    https_url = _html(https_verify_url(domain.domain))
    short_dns_host = _html("_geo-verify")
    domain_id = int(domain.domain_id)
    return (
        f'<li class="domain-row domain-row-pending"><strong>{domain_name}</strong> · {status}'
        '<div class="domain-verify-inline">'
        '<div class="verify-option verify-option-dns">'
        '<span class="verify-option-title">Option 1 · DNS TXT record</span>'
        '<p class="verify-option-copy">In your domain DNS settings, create one new TXT record with these fields.</p>'
        '<dl class="verify-field-grid">'
        '<div class="verify-field-row"><dt>Type</dt><dd><code>TXT</code></dd></div>'
        f'<div class="verify-field-row"><dt>Name / Host</dt><dd><code>{dns_host}</code></dd></div>'
        f'<div class="verify-field-row"><dt>Value / Content</dt><dd><code>{verify_value}</code></dd></div>'
        "</dl>"
        f'<p class="verify-provider-note">If your DNS provider already appends the domain, enter only '
        f"<code>{short_dns_host}</code> for Name / Host.</p>"
        "</div>"
        '<div class="verify-option verify-option-https">'
        '<span class="verify-option-title">Option 2 · HTTPS verification file</span>'
        '<p class="verify-option-copy">If DNS is hard to change, upload this file on your website instead.</p>'
        '<dl class="verify-field-grid">'
        f'<div class="verify-field-row"><dt>File URL</dt><dd><code>{https_url}</code></dd></div>'
        f'<div class="verify-field-row"><dt>File contents</dt><dd><code>{verify_value}</code></dd></div>'
        "</dl>"
        "</div>"
        '<div class="verify-actions">'
        f'<button data-domain-id="{domain_id}" data-method="dns" class="verify-btn" type="button">Check DNS record</button>'
        f'<button data-domain-id="{domain_id}" data-method="https" class="verify-btn" type="button">Check HTTPS file</button>'
        "</div></div></li>"
    )


def _run_list_item(run) -> str:
    """Render a concise platform run row for the dashboard."""
    score = "--" if run.score is None else f"{run.score}/100"
    detail = _run_summary_label(run)
    return (
        '<li class="platform-run-row">'
        f"<span><strong>{_html(run.kind.replace('_', ' ').title())}</strong> · {_html(run.domain)}</span>"
        f'<span class="run-status run-status-{_html(run.status)}">{_html(run.status)}</span>'
        f"<span>{_html(score)}</span>"
        f"<small>{_html(detail)}</small>"
        "</li>"
    )


def _run_summary_label(run: PlatformRun) -> str:
    """Return a human-readable run summary, including JSON-backed sitemap runs."""
    if run.result_summary:
        try:
            payload = json.loads(run.result_summary)
        except json.JSONDecodeError:
            return run.result_summary
        if isinstance(payload, dict) and payload.get("kind") == "sitemap_audit":
            audited = payload.get("audited_urls", 0)
            successful = payload.get("successful_urls", 0)
            failed = payload.get("failed_urls", 0)
            return f"{audited} pages audited · {successful} ok · {failed} failed"
    return run.result_summary or run.error or run.status


def _latest_sitemap_pages_html(runs) -> str:
    """Render latest saved sitemap audit pages for initial dashboard load."""
    for run in runs:
        if run.kind != "sitemap_audit" or not run.result_summary:
            continue
        try:
            payload = json.loads(run.result_summary)
        except json.JSONDecodeError:
            continue
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if isinstance(pages, list) and pages:
            return _sitemap_pages_html(pages)
    return '<li class="page-audit-empty">Run a sitemap audit to review each page.</li>'


def _page_audit_records_html(pages) -> str:
    payload = []
    for page in pages[:50]:
        payload.append(
            {
                "page_url": page.page_url,
                "score": page.score,
                "band": page.band,
                "error": page.error,
                "recommendations": page.recommendations,
                "title_issues": page.title_issues,
                "meta_issues": page.meta_issues,
                "schema_issues": page.schema_issues,
                "previous_score": page.previous_score,
                "score_delta": page.score_delta,
            }
        )
    return (
        _sitemap_pages_html(payload)
        if payload
        else '<li class="page-audit-empty">Run a sitemap audit to review each page.</li>'
    )


def _sitemap_pages_html(pages: Sequence[object]) -> str:
    html = ""
    for raw_page in pages[:25]:
        if not isinstance(raw_page, dict):
            continue
        url = str(raw_page.get("page_url") or raw_page.get("url") or "")
        score = raw_page.get("score", 0)
        band = str(raw_page.get("band", ""))
        error = str(raw_page.get("error") or "")
        recs = raw_page.get("recommendations") or []
        previous_score = raw_page.get("previous_score")
        delta = raw_page.get("score_delta")
        delta_label = ""
        if delta is not None:
            try:
                numeric_delta = int(delta)
                delta_label = f" ({'+' if numeric_delta > 0 else ''}{numeric_delta})"
            except (TypeError, ValueError):
                delta_label = ""
        score_detail = f"After {_html(score)}/100"
        if previous_score is not None:
            score_detail = f"Before {_html(previous_score)}/100 -> after {_html(score)}/100"
        if delta_label:
            score_detail = f"{score_detail} · delta {_html(delta_label.strip(' ()'))}"
        rec_html = ""
        if isinstance(recs, list) and recs:
            rec_html = "<ul>" + "".join(f"<li>{_html(str(rec))}</li>" for rec in recs[:5]) + "</ul>"
        elif error:
            rec_html = f"<p>{_html(error)}</p>"
        else:
            rec_html = "<p>No priority recommendations returned for this page.</p>"
        html += (
            '<li class="page-audit-row">'
            f"<div><strong>{_html(url)}</strong><span>{_html(band or 'unknown')}</span></div>"
            f"<em>{score_detail}</em>"
            f"<details><summary>Review page fixes</summary>{rec_html}</details>"
            "</li>"
        )
    return html or '<li class="page-audit-empty">No sitemap pages were audited.</li>'


def _weekly_report_item(report) -> str:
    """Render a concise weekly report row for the dashboard."""
    score = "--" if report.score is None else f"{report.score}/100"
    detail = report.summary or report.status
    delta_copy = "Before/after deltas by URL and prompt are included when page audits and benchmarks exist."
    return (
        '<li class="platform-run-row">'
        f"<span><strong>Weekly evidence</strong> · {_html(report.domain)}</span>"
        f'<span class="run-status run-status-{_html(report.status)}">{_html(report.status)}</span>'
        f"<span>{_html(score)}</span>"
        f"<small>{_html(detail)}</small>"
        f"<small>{_html(delta_copy)}</small>"
        "</li>"
    )


def _index_event_item(event) -> str:
    """Render one Index telemetry event in the dashboard."""
    badges = [event.source_type]
    if event.top_recommendation:
        badges.append("top")
    if event.cited:
        badges.append("cited")
    elif event.surfaced:
        badges.append("surfaced")
    else:
        badges.append("missed")
    badge_html = "".join(f'<span class="run-status">{_html(badge)}</span>' for badge in badges)
    rank = f"#{event.cited_rank}" if event.cited_rank else "--"
    label = event.query or event.page_url or event.cited_url or event.source_type
    artifact = event.evidence_artifact_id or "no artifact"
    evidence_bits = []
    if isinstance(event.evidence, dict):
        for key, value in list(event.evidence.items())[:4]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                evidence_bits.append(f"<span>{_html(key)}: {_html(value)}</span>")
    evidence_html = "".join(evidence_bits)
    return (
        '<li class="evidence-review-card">'
        '<div class="evidence-review-head">'
        f"<span><strong>{_html(event.agent or 'unknown')}</strong> · {_html(label)}</span>"
        f'<span class="evidence-rank">{_html(rank)}</span>'
        "</div>"
        f'<div class="evidence-badges">{badge_html}</div>'
        f"<p>{_html(event.answer_excerpt or event.page_url or 'No answer excerpt recorded.')}</p>"
        '<div class="evidence-meta">'
        f"<span>artifact <code>{_html(artifact)}</code></span>"
        f"<span>{event.value_units:.2f} value units</span>"
        f"{'<span>cited ' + _html(event.cited_url) + '</span>' if event.cited_url else ''}"
        "</div>"
        f'<div class="evidence-raw">{evidence_html}</div>'
        "</li>"
    )


def _dict_list(values: dict, *, suffix: str = "") -> str:
    if not values:
        return "<li>None</li>"
    return "".join(
        f"<li><span>{_html(key)}</span><strong>{_html(value)}{suffix}</strong></li>" for key, value in values.items()
    )


def _index_trend_bars(points: list[IndexTrendPoint]) -> str:
    if not points:
        return '<div class="trend-empty">No trend data yet</div>'
    max_events = max(int(point.get("events", 0) or 0) for point in points) or 1
    bars = []
    for point in points[-14:]:
        events = int(point.get("events", 0) or 0)
        height = max(8, int((events / max_events) * 72))
        bars.append(
            '<div class="trend-bar">'
            f'<span style="height:{height}px"></span>'
            f"<small>{_html(str(point.get('date', ''))[5:] or point.get('date', ''))}</small>"
            "</div>"
        )
    return "".join(bars)


def _action_plan_html(plan: dict[str, object]) -> str:
    priority = _html(plan.get("priority", "Collect AI answer evidence"))
    next_step = _html(plan.get("next_step", "Run a benchmark or paste an AI answer for target queries."))
    source = _html(plan.get("source", "arXiv:2605.25517"))
    fix_order = plan.get("fix_order", [])
    if not isinstance(fix_order, list):
        fix_order = []
    chips = "".join(f"<span>{_html(item)}</span>" for item in fix_order[:8])
    return (
        '<div class="index-action-plan" id="index-action-plan-live">'
        f"<p><strong data-plan-priority>{priority}</strong></p>"
        f"<p data-plan-next>{next_step}</p>"
        f'<div class="index-action-chips" data-plan-chips>{chips}</div>'
        f"<small>Decision loop source: {source}</small>"
        "</div>"
    )


def _render_index_page(request: Request, token: str) -> str:
    dash = _get_service().dashboard(token)
    summary = dash.index_summary
    html = _render_template(request, "index.html")
    html = html.replace("{{ORG_NAME}}", _html(dash.organization.name))
    html = html.replace("{{EMAIL}}", _html(dash.user.email))
    html = html.replace(
        "{{DOMAIN}}", _html(summary.domain or dash.primary_verified_domain or dash.organization.email_domain)
    )
    html = html.replace("{{INDEX_EVENTS}}", _html(summary.total_events))
    html = html.replace("{{INDEX_CITATION_RATE}}", _html(f"{summary.citation_rate:.0%}"))
    html = html.replace("{{INDEX_TOP_RATE}}", _html(f"{summary.top_recommendation_rate:.0%}"))
    html = html.replace("{{INDEX_VALUE_UNITS}}", _html(f"{summary.total_value_units:.2f}"))
    html = html.replace("{{SOURCE_COVERAGE}}", _dict_list(summary.source_coverage))
    html = html.replace("{{AGENT_COVERAGE}}", _dict_list(summary.agent_coverage))
    html = html.replace("{{TOP_QUERIES}}", _dict_list(summary.top_queries))
    html = html.replace("{{TOP_PAGES}}", _dict_list(summary.top_pages))
    html = html.replace("{{TOP_CITED_PAGES}}", _dict_list(summary.top_cited_pages))
    html = html.replace("{{MISSED_QUERIES}}", _dict_list(summary.missed_queries))
    html = html.replace("{{TREND_BARS}}", _index_trend_bars(summary.trend_points))
    html = html.replace("{{ACTION_PLAN}}", _action_plan_html(summary.action_plan))
    events_html = "".join(_index_event_item(event) for event in summary.recent_events)
    html = html.replace("{{INDEX_RECENT_EVENTS}}", events_html or "<li>No agent usage events yet.</li>")
    return html


def _public_index_preview_html(request: Request, payload: dict) -> str:
    """Render the no-auth domain preview page."""
    domain = _html(payload.get("domain", ""))
    claimed = "Verified" if payload.get("verified") else ("Claim started" if payload.get("claimed") else "Unclaimed")
    claim_path = _html(payload.get("claim_path", "/platform/register"))
    nonce = _nonce_attr(request)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GEOSITION Index · {domain}</title>
  <link rel="stylesheet" href="/platform/assets/site.css" />
</head>
<body>
  <main class="preview-shell">
    <section class="dash-panel preview-panel">
      <p class="msg">GEOSITION Index preview</p>
      <h1>{domain}</h1>
      <div class="visibility-metrics">
        <div class="visibility-metric"><span>Claim status</span><strong>{_html(claimed)}</strong></div>
        <div class="visibility-metric"><span>Telemetry</span><strong>Locked</strong></div>
        <div class="visibility-metric"><span>Next step</span><strong>Verify</strong></div>
      </div>
      <p class="msg">Claim this domain to unlock AI answer usage, citation value units, benchmark evidence, and fix priority.</p>
      <a class="btn btn-primary" href="{claim_path}">Claim this domain</a>
    </section>
  </main>
  <script{nonce}>document.documentElement.dataset.preview = 'index';</script>
</body>
</html>"""


@router.api_route("/platform/assets/site.css", methods=["GET", "HEAD"])
async def platform_site_css() -> Response:
    """Shared stylesheet for platform marketing and auth pages."""
    css = (_TEMPLATES / "site.css").read_text(encoding="utf-8")
    return _cacheable_response(css, "text/css")


@router.api_route("/platform/assets/cobe.esm.js", methods=["GET", "HEAD"])
async def platform_cobe_js() -> Response:
    """Self-hosted COBE globe renderer for the platform landing page."""
    path = _PLATFORM_ASSETS / "cobe.esm.js"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return _cacheable_response(path.read_text(encoding="utf-8"), "text/javascript")


@router.api_route("/platform/assets/hero-bg.png", methods=["GET", "HEAD"])
async def platform_hero_bg() -> Response:
    """Hero background stipple mountain art."""
    path = _PLATFORM_ASSETS / "hero-bg.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return _cacheable_response(path.read_bytes(), "image/png")


_ASSET_MEDIA_TYPES = {
    ".css": "text/css",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".js": "text/javascript",
    ".map": "application/json",
    ".txt": "text/plain",
}


@router.api_route("/platform/assets/{asset_name:path}", methods=["GET", "HEAD"])
async def platform_asset(asset_name: str) -> Response:
    """Static images and other platform marketing assets."""
    suffix = Path(asset_name).suffix.lower()
    if suffix not in _ASSET_MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="Not found")
    path = (_PLATFORM_ASSETS / asset_name).resolve()
    try:
        path.relative_to(_PLATFORM_ASSETS.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return _cacheable_response(path.read_bytes(), _ASSET_MEDIA_TYPES[suffix])


def _session_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return cast(str, auth[7:].strip())
    return cast(Optional[str], request.cookies.get("geo_session"))


def _secure_cookie(request: Request) -> bool:
    forced = os.environ.get("GEOSITION_SECURE_COOKIES", "").strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    if forced in {"0", "false", "no", "off"}:
        return False
    return cast(bool, request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https")


def require_token(request: Request) -> str:
    token = _session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        _get_service().require_session(token)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    return token


def require_write_token(request: Request) -> str:
    _enforce_platform_rate_limit(request)
    _validate_csrf(request)
    return require_token(request)


def require_expensive_write_token(request: Request) -> str:
    _enforce_platform_rate_limit(request, bucket="expensive")
    _validate_csrf(request)
    return require_token(request)


def require_worker_token(request: Request) -> str:
    configured = os.environ.get("GEOSITION_WORKER_TOKEN", "").strip()
    provided = request.headers.get("X-GEOSITION-Worker-Token", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Hosted worker token is not configured")
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(status_code=403, detail="Invalid hosted worker token")
    _enforce_platform_rate_limit(request, bucket="expensive")
    return cast(str, provided)


# ─── HTML pages ───────────────────────────────────────────────────────────────


@router.api_route("/platform", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_home(request: Request):
    """Platform marketing landing; signed-in users go to dashboard."""
    token = _session_token(request)
    if token:
        try:
            _get_service().require_session(token)
            return RedirectResponse("/platform/dashboard", status_code=302)
        except PermissionError:
            pass
    return _attach_csrf_cookie(HTMLResponse(_render_template(request, "landing.html")), request)


@router.api_route("/gestion-velora", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def gestion_velora_page(request: Request):
    """Public profile for Gestion Velora, a Greater Montreal property manager."""
    return HTMLResponse(_render_template(request, "gestion-velora.html"))


@router.api_route("/platform/register", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_register_page(request: Request):
    return _attach_csrf_cookie(HTMLResponse(_render_template(request, "register.html")), request)


@router.api_route("/platform/login", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_login_page(request: Request):
    return _attach_csrf_cookie(HTMLResponse(_render_template(request, "login.html")), request)


@router.api_route("/platform/forgot-password", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_forgot_password_page(request: Request):
    return _attach_csrf_cookie(HTMLResponse(_render_template(request, "forgot-password.html")), request)


@router.api_route("/platform/reset-password", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_reset_password_page(request: Request):
    return _attach_csrf_cookie(HTMLResponse(_render_template(request, "reset-password.html")), request)


@router.api_route("/platform/index/check", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_index_check_page(request: Request, domain: str = ""):
    """Public domain-intelligence preview for content owners."""
    try:
        payload = _get_service().public_index_preview(domain)
    except ValueError:
        payload = {
            "domain": "",
            "claimed": False,
            "verified": False,
            "claim_path": "/platform/register",
        }
    return _attach_csrf_cookie(HTMLResponse(_public_index_preview_html(request, payload)), request)


@router.api_route("/platform/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_dashboard_page(request: Request):
    token = _session_token(request)
    if not token:
        return RedirectResponse("/platform/login", status_code=302)
    try:
        dash = _get_service().dashboard(token)
    except PermissionError:
        return RedirectResponse("/platform/login", status_code=302)
    html = _render_template(request, "dashboard.html")
    has_verified_domain = any(domain.status == "verified" for domain in dash.domains)
    display_domain = dash.target_domain
    html = html.replace("{{BODY_ATTR}}", "" if has_verified_domain else ' class="workspace-locked"')
    html = html.replace("{{VERIFY_BANNER_ATTR}}", " hidden" if has_verified_domain else "")
    html = html.replace("{{ORG_NAME}}", _html(dash.organization.name))
    html = html.replace("{{EMAIL}}", _html(dash.user.email))
    html = html.replace("{{EMAIL_DOMAIN}}", _html(dash.organization.email_domain))
    html = html.replace("{{DISPLAY_DOMAIN}}", _html(display_domain))
    domains_html = ""
    for domain in dash.domains:
        domains_html += _domain_list_item(domain)
    if not domains_html:
        domains_html = "<li>No website added yet.</li>"
    html = html.replace("{{DOMAINS}}", domains_html)
    benchmarks_html = ""
    for run in dash.recent_benchmarks:
        benchmarks_html += (
            f"<li>#{run.benchmark_run_id} {_html(run.domain)} · {run.benchmark_score}/100 ({_html(run.band)})</li>"
        )
    if not benchmarks_html:
        benchmarks_html = "<li>No benchmark runs yet.</li>"
    html = html.replace("{{BENCHMARKS}}", benchmarks_html)
    runs_html = ""
    for platform_run in dash.recent_runs:
        runs_html += _run_list_item(platform_run)
    if not runs_html:
        runs_html = "<li>No platform runs yet.</li>"
    html = html.replace("{{RUNS}}", runs_html)
    html = html.replace("{{SITEMAP_PAGES}}", _page_audit_records_html(dash.recent_page_audits))
    weekly_reports_html = ""
    for report in dash.recent_weekly_reports:
        weekly_reports_html += _weekly_report_item(report)
    if not weekly_reports_html:
        weekly_reports_html = "<li>No weekly evidence reports yet.</li>"
    html = html.replace("{{WEEKLY_REPORTS}}", weekly_reports_html)
    summary = dash.index_summary
    html = html.replace("{{INDEX_EVENTS}}", _html(summary.total_events))
    html = html.replace("{{INDEX_CITATION_RATE}}", _html(f"{summary.citation_rate:.0%}"))
    html = html.replace("{{INDEX_TOP_RATE}}", _html(f"{summary.top_recommendation_rate:.0%}"))
    html = html.replace("{{INDEX_VALUE_UNITS}}", _html(f"{summary.total_value_units:.2f}"))
    html = html.replace("{{INDEX_ACTION_PLAN}}", _action_plan_html(summary.action_plan))
    index_events_html = ""
    for event in summary.recent_events:
        index_events_html += _index_event_item(event)
    if not index_events_html:
        index_events_html = "<li>No agent usage events yet.</li>"
    html = html.replace("{{INDEX_RECENT_EVENTS}}", index_events_html)
    return _attach_csrf_cookie(HTMLResponse(html), request)


@router.api_route("/platform/index", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def platform_index_page(request: Request):
    token = _session_token(request)
    if not token:
        return RedirectResponse("/platform/login", status_code=302)
    try:
        return _attach_csrf_cookie(HTMLResponse(_render_index_page(request, token)), request)
    except PermissionError:
        return RedirectResponse("/platform/login", status_code=302)


# ─── JSON API ─────────────────────────────────────────────────────────────────


@router.post("/api/v1/auth/register")
async def api_register(body: RegisterBody, request: Request):
    _enforce_platform_rate_limit(request, bucket="auth")
    try:
        service = _get_service()
        payload = service.register(email=body.email, password=body.password, org_name=body.org_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Platform registration failed")
        raise HTTPException(status_code=500, detail="Registration failed. Try again soon.") from exc
    if body.domain.strip():
        try:
            payload["domain_verification"] = service.add_website_domain(
                payload["session"]["token"],
                body.domain,
            )
        except ValueError as exc:
            payload["domain_error"] = str(exc)
        except RuntimeError as exc:
            raise _platform_service_http_error(exc) from exc
        except Exception as exc:
            _logger.exception("Platform domain registration failed")
            raise HTTPException(status_code=500, detail="Domain registration failed. Try again soon.") from exc
    response = JSONResponse(payload)
    _set_session_cookies(response, request, payload["session"]["token"])
    return response


@router.post("/api/v1/auth/login")
async def api_login(body: LoginBody, request: Request):
    _enforce_platform_rate_limit(request, bucket="auth")
    try:
        payload = _get_service().login(email=body.email, password=body.password)
        response = JSONResponse(payload)
        _set_session_cookies(response, request, payload["session"]["token"])
        return response
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Platform login failed")
        raise HTTPException(status_code=500, detail="Login failed. Try again soon.") from exc


@router.post("/api/v1/auth/forgot-password")
async def api_forgot_password(body: ForgotPasswordBody, request: Request):
    _enforce_platform_rate_limit(request, bucket="auth")
    try:
        return _get_service().request_password_reset(
            email=body.email,
            base_url=str(request.base_url),
        )
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Platform password reset request failed")
        raise HTTPException(status_code=500, detail="Password reset request failed. Try again soon.") from exc


@router.post("/api/v1/auth/reset-password")
async def api_reset_password(body: ResetPasswordBody, request: Request):
    _enforce_platform_rate_limit(request, bucket="auth")
    try:
        return _get_service().reset_password(token=body.token, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Platform password reset failed")
        raise HTTPException(status_code=500, detail="Password reset failed. Try again soon.") from exc


@router.post("/api/v1/auth/logout")
async def api_logout(token: str = Depends(require_write_token)):
    _get_service().logout(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("geo_session", path="/")
    response.delete_cookie(_CSRF_COOKIE, path="/")
    return response


@router.get("/api/v1/me")
async def api_me(token: str = Depends(require_token)):
    dash = _get_service().dashboard(token)
    return {
        "user": {
            "email": dash.user.email,
            "email_domain": dash.user.email_domain,
        },
        "organization": {
            "name": dash.organization.name,
            "email_domain": dash.organization.email_domain,
            "slug": dash.organization.slug,
        },
        "primary_verified_domain": dash.primary_verified_domain,
        "target_domain": dash.target_domain,
    }


@router.get("/api/v1/storage/health")
async def api_storage_health(token: str = Depends(require_token)):
    try:
        return _get_service().storage_health(token)
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.get("/api/v1/platform/health")
async def api_platform_health(_worker_token: str = Depends(require_worker_token)):
    try:
        return _get_service().production_health_check()
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.get("/api/v1/dashboard")
async def api_dashboard(token: str = Depends(require_token)):
    dash = _get_service().dashboard(token)
    from dataclasses import asdict

    return {
        "organization": asdict(dash.organization),
        "user": asdict(dash.user),
        "domains": [asdict(d) for d in dash.domains],
        "primary_verified_domain": dash.primary_verified_domain,
        "target_domain": dash.target_domain,
        "competitors": [asdict(c) for c in dash.competitors],
        "prompts": [asdict(p) for p in dash.prompts],
        "recent_benchmarks": [asdict(b) for b in dash.recent_benchmarks],
        "recent_runs": [asdict(r) for r in dash.recent_runs],
        "recent_page_audits": [asdict(p) for p in dash.recent_page_audits],
        "recent_weekly_reports": [asdict(r) for r in dash.recent_weekly_reports],
        "index_summary": asdict(dash.index_summary),
        "agency_loop": asdict(dash.agency_loop),
    }


@router.get("/api/v1/runs")
async def api_platform_runs(kind: str = "", token: str = Depends(require_token)):
    return _get_service().list_runs(token, kind=kind.strip().lower())


@router.get("/api/v1/reports/weekly")
async def api_weekly_reports(domain: str = "", limit: int = 12, token: str = Depends(require_token)):
    try:
        return {"reports": _get_service().list_weekly_reports(token, domain=domain, limit=limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/reports/weekly/latest")
async def api_weekly_report_latest(domain: str = "", token: str = Depends(require_token)):
    try:
        report = _get_service().latest_weekly_report(token, domain=domain)
        return {"report": report}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/reports/weekly/run")
async def api_weekly_report_run(body: WeeklyReportBody, token: str = Depends(require_expensive_write_token)):
    provider = body.lighthouse_provider.strip().lower() or "none"
    if provider not in {"pagespeed", "cli", "none"}:
        raise HTTPException(status_code=400, detail="lighthouse_provider must be pagespeed, cli, or none")
    answers = body.answers if isinstance(body.answers, (dict, list)) else None
    try:
        return _get_service().run_weekly_evidence_report(
            token,
            domain=body.domain,
            answers_payload=answers,
            lighthouse_provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Weekly report run failed")
        raise HTTPException(
            status_code=502,
            detail="Weekly report could not complete live collection right now. Try again after audit data is available.",
        ) from exc


@router.post("/api/v1/domains")
async def api_add_domain(body: DomainBody, token: str = Depends(require_write_token)):
    try:
        return _get_service().add_website_domain(token, body.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/domains/{domain_id}/verify")
async def api_verify_domain(domain_id: int, body: VerifyBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().check_domain_verification(token, domain_id, method=body.method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/competitors")
async def api_add_competitor(body: CompetitorBody, token: str = Depends(require_write_token)):
    try:
        return _get_service().add_competitor(token, body.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/prompts")
async def api_add_prompt(body: PromptBody, token: str = Depends(require_write_token)):
    try:
        return _get_service().add_prompt(
            token,
            query_text=body.query_text,
            external_id=body.external_id,
            query_class=body.query_class,
            keyword_topic=body.keyword_topic,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/audit")
async def api_audit(body: DomainBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().run_site_audit(token, body.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Site audit failed")
        raise HTTPException(
            status_code=502,
            detail="Site audit could not complete right now. Check the domain is publicly reachable and try again.",
        ) from exc


@router.post("/api/v1/audit/sitemap")
async def api_sitemap_audit(body: SitemapAuditBody, token: str = Depends(require_expensive_write_token)):
    try:
        service = _get_service()
        if body.run_now:
            return await asyncio.to_thread(
                service.run_sitemap_audit,
                token,
                domain=body.domain,
                sitemap_url=body.sitemap_url,
                max_urls=body.max_urls,
            )
        return service.queue_sitemap_audit(
            token,
            domain=body.domain,
            sitemap_url=body.sitemap_url,
            max_urls=body.max_urls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Sitemap audit failed")
        raise HTTPException(
            status_code=502,
            detail="Page audit could not complete right now. Check the sitemap URL and try again.",
        ) from exc


@router.post("/api/v1/audit/sitemap/run")
async def api_sitemap_audit_run(body: HostedCollectionBody, _worker_token: str = Depends(require_worker_token)):
    try:
        return await asyncio.to_thread(_get_service().run_next_sitemap_audit, domain=body.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Sitemap audit worker failed")
        raise HTTPException(status_code=502, detail="Queued page audit worker failed. Try again soon.") from exc


@router.get("/api/v1/audit/pages")
async def api_page_audits(
    domain: str = "",
    run_id: Optional[int] = None,  # noqa: UP045 - Pydantic/typing compatibility on Python 3.9.
    limit: int = 100,
    token: str = Depends(require_token),
):
    try:
        return _get_service().list_page_audits(token, domain=domain, run_id=run_id, limit=max(1, min(limit, 200)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/audit/pages/history")
async def api_page_audit_history(body: PageAuditHistoryBody, token: str = Depends(require_token)):
    try:
        return _get_service().page_audit_history(token, page_url=body.page_url, limit=body.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/visibility/summary")
async def api_visibility_summary(domain: str = "", token: str = Depends(require_token)):
    try:
        return _get_service().citation_share_summary(token, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/measurement/search")
async def api_search_measurement(body: SearchMeasurementBody, token: str = Depends(require_expensive_write_token)):
    """Fetch provider-owned search data without saving provider credentials."""
    from geo_optimizer.core.search_measurement import fetch_search_measurement, validate_property

    try:
        service = _get_service()
        domain = service.require_verified_domain(token, body.domain)
        validate_property(body.provider, body.property_id, domain)
        result = await asyncio.to_thread(
            fetch_search_measurement,
            body.provider,
            body.property_id,
            body.access_token,
            body.start_date,
            body.end_date,
        )
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/search-connections/start")
async def api_search_connection_start(
    body: SearchConnectionBody, request: Request, token: str = Depends(require_write_token)
):
    from geo_optimizer.saas.search_connections import begin_connection

    try:
        domain = _get_service().require_verified_domain(token, body.domain)
        url, state = begin_connection(body.provider, domain, token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = JSONResponse({"authorization_url": url}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        "geo_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/api/v1/search-connections/callback",
    )
    return response


@router.get("/api/v1/search-connections/callback/{provider}")
async def api_search_connection_callback(provider: str, request: Request, token: str = Depends(require_token)):
    from geo_optimizer.saas.search_connections import exchange_code, save_connection, sync_connection, verify_state

    try:
        state = verify_state(
            provider, request.query_params.get("state", ""), request.cookies.get("geo_oauth_state", ""), token
        )
        code = request.query_params.get("code", "")
        if not code or len(code) > 4096:
            raise ValueError("Access was not granted. Please try connecting again.")
        service = _get_service()
        domain = service.require_verified_domain(token, str(state["domain"]))
        _, org = service.require_session(token)
        tokens = await asyncio.to_thread(exchange_code, provider, code)
        await asyncio.to_thread(save_connection, service.store, org.org_id, domain, provider, tokens)
        rows = service.store.list_search_connections(org.org_id)
        connection = next(row for row in rows if row["domain"] == domain and row["provider"] == provider)
        try:
            await asyncio.to_thread(sync_connection, service.store, connection)
        except Exception:
            from datetime import datetime, timezone

            service.store.mark_search_connection_error(
                org.org_id, domain, provider, datetime.now(timezone.utc).isoformat()
            )
        location = "/platform/dashboard?search_connection=connected"
    except (ValueError, RuntimeError, KeyError, StopIteration):
        location = "/platform/dashboard?search_connection=failed"
    response = RedirectResponse(
        location, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
    response.delete_cookie("geo_oauth_state", path="/api/v1/search-connections/callback")
    return response


@router.get("/api/v1/search-connections")
async def api_search_connections(domain: str, token: str = Depends(require_token)):
    try:
        service = _get_service()
        normalized = service.require_verified_domain(token, domain)
        _, org = service.require_session(token)
        rows = service.store.list_search_connections(org.org_id)
        connections = [
            {
                "provider": row["provider"],
                "property": row["property_id"],
                "status": row["status"],
                "last_synced_at": row["last_synced_at"],
                "result": json.loads(row["last_result_json"] or "{}"),
            }
            for row in rows
            if row["domain"] == normalized
        ]
        return JSONResponse({"connections": connections}, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/search-connections/disconnect")
async def api_search_connection_disconnect(body: SearchConnectionBody, token: str = Depends(require_write_token)):
    if body.provider not in ("google", "bing"):
        raise HTTPException(status_code=400, detail="Unsupported search provider.")
    try:
        service = _get_service()
        domain = service.require_verified_domain(token, body.domain)
        _, org = service.require_session(token)
        service.store.delete_search_connection(org.org_id, domain, body.provider)
        return {"status": "disconnected"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/search-connections/scheduled-sync")
async def api_search_connection_scheduled_sync(request: Request):
    from datetime import datetime, timedelta, timezone

    from geo_optimizer.saas.search_connections import sync_connection

    expected = os.environ.get("CRON_SECRET", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not secrets.compare_digest(supplied, "Bearer " + expected):
        raise HTTPException(status_code=403, detail="Invalid scheduler token")
    service = _get_service()
    now = datetime.now(timezone.utc)
    completed, failed = 0, 0
    for row in service.store.list_search_connections():
        try:
            last = row.get("last_synced_at")
            if last and datetime.fromisoformat(last.replace("Z", "+00:00")) > now - timedelta(hours=23):
                continue
            # A removed or unverified workspace domain must not keep syncing.
            service._require_verified(row["org_id"], row["domain"])
            await asyncio.to_thread(sync_connection, service.store, row)
            completed += 1
        except Exception:
            failed += 1
            # Do not log provider responses or credentials.
            service.store.mark_search_connection_error(row["org_id"], row["domain"], row["provider"], now.isoformat())
    return {"synced": completed, "failed": failed}


@router.get("/api/v1/index/preview")
async def api_index_preview(domain: str = ""):
    try:
        return _get_service().public_index_preview(domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/index/summary")
async def api_index_summary(domain: str = "", token: str = Depends(require_token)):
    try:
        return _get_service().index_summary(token, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/index")
async def api_index(domain: str = "", token: str = Depends(require_token)):
    try:
        return _get_service().index_summary(token, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/index/value-ledger")
async def api_index_value_ledger(domain: str = "", token: str = Depends(require_token)):
    try:
        return _get_service().value_ledger(token, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/collection/status")
async def api_collection_status(domain: str = "", token: str = Depends(require_token)):
    try:
        return _get_service().collection_status(token, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/collection/start")
async def api_collection_start(body: HostedCollectionBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().queue_hosted_collection(
            token,
            domain=body.domain,
            providers=body.providers or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _platform_internal_error("Hosted collection queue failed", exc) from exc


@router.post("/api/v1/collection/run")
async def api_collection_run(body: HostedCollectionBody, _worker_token: str = Depends(require_worker_token)):
    try:
        return _get_service().run_next_hosted_collection(
            domain=body.domain,
            providers=body.providers or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _platform_internal_error("Hosted collection run failed", exc) from exc


@router.post("/api/v1/index/retrieval/probe")
async def api_index_retrieval_probe(body: RetrievalProbeBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().retrieval_probe(token, domain=body.domain, query=body.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/index/serp-check")
async def api_index_serp_check(body: SerpCheckBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().run_serp_check(token, domain=body.domain, keyword=body.keyword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _platform_internal_error("SERP check failed", exc) from exc


@router.get("/api/v1/index/benchmark-harness")
async def api_index_benchmark_harness():
    return _get_service().benchmark_harness()


@router.post("/api/v1/index/events")
async def api_index_event(body: IndexEventBody, token: str = Depends(require_write_token)):
    try:
        payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        return _get_service().record_agent_usage(token, event=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/index/crawler-log")
async def api_index_crawler_log(body: IndexCrawlerLogBody, token: str = Depends(require_expensive_write_token)):
    try:
        return _get_service().import_crawler_log(
            token,
            domain=body.domain,
            log_text=body.log_text,
            evidence_artifact_id=body.evidence_artifact_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc


@router.post("/api/v1/benchmark/run")
async def api_benchmark_run(request: Request, token: str = Depends(require_expensive_write_token)):
    """Run benchmark; body may be large (answers JSON)."""
    raw = await request.body()
    if len(raw) > _PLATFORM_MAX_BODY:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    domain = str(payload.get("domain", "")).strip()
    answers = payload.get("answers", payload)
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required")
    try:
        return _get_service().run_benchmark(token, domain=domain, answers_payload=answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _platform_service_http_error(exc) from exc
    except Exception as exc:
        _logger.exception("Benchmark run failed")
        raise HTTPException(
            status_code=502,
            detail="Benchmark could not complete right now. Check answers JSON and try again.",
        ) from exc

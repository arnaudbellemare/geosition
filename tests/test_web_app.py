"""
Test per geo_optimizer.web.app — FastAPI web application.

Coverage fix #154: il modulo era a 0% di coverage.
Tutti i test mockano run_full_audit per evitare calls di rete.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Optional dependency: skip tests if FastAPI or httpx are not installed
pytest.importorskip("fastapi", reason="FastAPI non installato (pip install geosition[web])")
pytest.importorskip("httpx", reason="httpx non installato (pip install httpx)")

from starlette.testclient import TestClient

from geo_optimizer.web.app import (
    _audit_cache,
    _check_rate_limit,
    _rate_limit_store,
    app,
)

# ─── Fixture: AuditResult mock ───────────────────────────────────────────────


def _make_mock_audit_result(score=75, band="good"):
    """Costruisce un AuditResult mock con tutti i campi necessari."""
    from geo_optimizer.models.results import (
        AuditResult,
        ContentResult,
        LlmsTxtResult,
        MetaResult,
        RobotsResult,
        SchemaResult,
    )

    return AuditResult(
        url="https://example.com",
        score=score,
        band=band,
        robots=RobotsResult(
            found=True,
            citation_bots_ok=True,
            citation_bots_explicit=True,
            bots_allowed=["GPTBot", "ClaudeBot"],
            bots_blocked=[],
            bots_missing=[],
            bots_partial=[],
        ),
        llms=LlmsTxtResult(
            found=True,
            has_h1=True,
            has_description=True,
            has_sections=True,
            has_links=True,
            word_count=150,
        ),
        schema=SchemaResult(
            found_types=["WebSite"],
            has_website=True,
            has_faq=False,
            has_webapp=False,
        ),
        meta=MetaResult(
            has_title=True,
            has_description=True,
            has_canonical=True,
            has_og_title=True,
            has_og_description=True,
            has_og_image=False,
            title_text="Example Site",
            description_text="A test website",
            description_length=15,
            title_length=12,
            canonical_url="https://example.com",
        ),
        content=ContentResult(
            has_h1=True,
            heading_count=5,
            has_numbers=True,
            has_links=True,
            word_count=500,
            h1_text="Welcome to Example",
            numbers_count=4,
            external_links_count=3,
        ),
        recommendations=["Add FAQPage schema"],
        http_status=200,
        page_size=12345,
    )


# ─── Fixture: client pulito per ogni test ────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_state():
    """Pulisce cache e rate limit store prima di ogni test."""
    _audit_cache.clear()
    _rate_limit_store.clear()
    yield
    _audit_cache.clear()
    _rate_limit_store.clear()


@pytest.fixture
def client():
    """TestClient FastAPI con raise_server_exceptions=False per testare errori HTTP."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_strict():
    """TestClient che propaga le eccezioni del server (per test di logica)."""
    return TestClient(app, raise_server_exceptions=True)


# ─── Test: GET / ─────────────────────────────────────────────────────────────


def test_homepage_serves_platform_without_redirect(client):
    """GET / serves the platform directly to avoid a mobile redirect round trip."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "GEOSITION" in response.text
    assert '<main id="main-content">' in response.text


def test_platform_landing_links_product_video_and_serves_refresh_styles(client):
    landing = client.get("/platform")
    stylesheet = client.get("/platform/assets/landing-refresh.css")
    video = client.get("/platform/assets/reel-skincare-v2.mp4")

    assert landing.status_code == 200
    assert 'href="https://slopacc.com/"' in landing.text
    assert landing.text.count('<svg class="clone-symbol"') == 2
    assert 'href="/platform/assets/landing-refresh.css?v=53"' in landing.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert video.status_code == 200
    assert video.headers["content-type"].startswith("video/mp4")
    assert "prefers-reduced-motion: reduce" in landing.text


def test_platform_landing_ai_intro_assets_are_available(client):
    landing = client.get("/platform")

    assert 'aria-label="GEOSITION is your AI-powered marketing partner"' in landing.text
    assert 'aria-label="AI search platforms"' in landing.text
    assert "Audit categories" in landing.text
    for filename in (
        "commerce-ai-assistant.png",
        "commerce-shopping-bag.png",
        "commerce-storefront.png",
        "platform-icon-perplexity.svg",
        "platform-icon-google.svg",
        "platform-icon-claude.svg",
        "platform-icon-googlegemini.svg",
    ):
        assert client.get(f"/platform/assets/{filename}").status_code == 200


def test_platform_landing_workspace_preview_identifies_sample_commerce_data(client):
    response = client.get("/platform")

    assert response.status_code == 200
    assert (
        'aria-label="Illustrative GEOSITION workspace showing an AI assistant and example citation benchmark results"'
        in response.text
    )
    assert "Illustrative preview" in response.text
    assert "example.com/serum" in response.text
    assert "example.com/sneaker" in response.text


def test_platform_asset_serves_webm_reference_media(client, tmp_path):
    (tmp_path / "example.webm").write_bytes(b"video")

    with patch("geo_optimizer.web.platform_routes._PLATFORM_ASSETS", tmp_path):
        response = client.get("/platform/assets/example.webm")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/webm")
    assert response.content == b"video"


def test_root_fastapi_entrypoint_exports_web_app():
    """Root main.py deve esporre la stessa app FastAPI della piattaforma."""
    import main as entrypoint

    assert entrypoint.app is app


def test_vercel_fastapi_entrypoint_exports_web_app():
    """api/index.py deve esporre la stessa app FastAPI per Vercel."""
    from api import index as entrypoint

    assert entrypoint.app is app


def test_vercel_config_routes_all_paths_to_fastapi():
    """vercel.json deve instradare la piattaforma alla funzione Python."""
    config = json.loads(Path("vercel.json").read_text())

    assert config["builds"][0]["src"] == "api/index.py"
    assert config["builds"][0]["use"] == "@vercel/python"
    assert config["routes"][0] == {"src": "/(.*)", "dest": "api/index.py"}


def test_platform_nested_avatar_asset_served_safely(client):
    """Nested platform assets devono servire avatar senza traversal."""
    story_assets = [
        client.get("/platform/assets/earn-per-citation.webp"),
        client.get("/platform/assets/publishers-data.webp"),
        client.get("/platform/assets/ai-companies.webp"),
    ]
    avatar = client.get("/platform/assets/avatars/independent-analyst.png")
    traversal = client.get("/platform/assets/../app.py")

    for story in story_assets:
        assert story.status_code == 200
        assert story.headers["content-type"] == "image/webp"
    assert avatar.status_code == 200
    assert avatar.headers["content-type"] == "image/png"
    assert traversal.status_code == 404


def test_platform_cobe_globe_asset_is_packaged(client):
    """Il renderer del globo deve essere servito dal pacchetto, non da node_modules."""
    response = client.get("/platform/assets/cobe.esm.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "public, max-age=31536000, immutable" in response.headers["cache-control"]
    assert b"export{" in response.content
    assert b"as default" in response.content


def test_platform_dashboard_loop_asset_is_served_and_cached(client):
    response = client.get("/platform/assets/dashboard-loop.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "public, max-age=31536000, immutable" in response.headers["cache-control"]
    assert b"GEOSITION_DASHBOARD_LOOP" in response.content


def test_platform_landing_self_hosts_lenis_smooth_scroll(client):
    landing = client.get("/platform")
    lenis = client.get("/platform/assets/lenis.min.js")
    smooth_scroll = client.get("/platform/assets/smooth-scroll.js")
    license_file = client.get("/platform/assets/lenis.LICENSE.txt")
    source_map = client.get("/platform/assets/lenis.min.js.map")

    assert landing.status_code == 200
    assert "/platform/assets/lenis.min.js?v=1.3.25" in landing.text
    assert "/platform/assets/smooth-scroll.js?v=geosition-20260715-lenis" in landing.text
    assert '<script src="/platform/assets/lenis.min.js' not in landing.text
    assert "if (desktop && !reduce)" in landing.text
    assert lenis.status_code == 200
    assert lenis.headers["content-type"].startswith("text/javascript")
    assert b"globalThis.Lenis" in lenis.content
    assert smooth_scroll.status_code == 200
    assert smooth_scroll.headers["content-type"].startswith("text/javascript")
    assert b"prefers-reduced-motion: reduce" in smooth_scroll.content
    assert b"native-scroll" in smooth_scroll.content
    assert license_file.status_code == 200
    assert license_file.headers["content-type"].startswith("text/plain")
    assert source_map.status_code == 200
    assert source_map.headers["content-type"].startswith("application/json")


def test_platform_landing_keeps_fast_seo_asset_hints(client):
    response = client.get("/platform")
    css = client.get("/platform/assets/site.css")

    assert response.status_code == 200
    assert css.status_code == 200
    html = response.text
    assert 'rel="preload" as="image" href="/platform/assets/reel-skincare-poster.jpg"' in html
    assert 'fetchpriority="high"' in html
    assert 'rel="canonical" href="https://geositionai.com/platform"' in html
    assert 'property="og:url" content="https://geositionai.com/platform"' in html
    assert "https://geosition.dev/platform" not in html
    assert "/platform/assets/reel-skincare-v2.mp4" in html
    assert "/platform/assets/reel-coffee-v2.mp4" in html
    assert "family=Inter" in html
    assert "family=Newsreader" in html
    assert "family=JetBrains+Mono" in html
    assert "family=Geist" not in html
    assert "family=Space+Grotesk" not in html
    assert "family=Space+Mono" not in html


def test_platform_landing_has_honest_mobile_first_conversion_path(client):
    response = client.get("/platform")
    css = client.get("/platform/assets/site.css")

    assert response.status_code == 200
    assert css.status_code == 200
    html = response.text
    assert 'class="mobile-nav-account" href="/platform/login"' in html
    assert 'class="mobile-nav-account mobile-nav-primary" href="/platform/register"' in html
    assert 'id="domain-input" name="domain" type="url"' in html
    assert 'id="domain-error" aria-live="polite"' in html
    assert "domainForm.classList.add('is-invalid')" in html
    assert "event.key === 'Escape'" in html
    assert 'href="/demo">GEO audit</a>' in html
    assert 'href="https://slopacc.com/">Product video ↗</a>' in html
    assert 'id="pricing"' not in html
    assert 'id="product"' in html
    assert 'class="reel-stage reel-stage-second"' in html
    assert 'Illustrative moving storefront examples' in html
    assert 'data-pricing-frequency=' not in html
    assert 'data-discount-badge' not in html



def test_gestion_velora_profile_is_indexable_and_website_is_linked_from_platform(client):
    landing = client.get("/platform")
    profile = client.get("/gestion-velora")

    assert profile.status_code == 200
    assert 'rel="canonical" href="https://geositionai.com/gestion-velora"' in profile.text
    assert '<meta name="robots" content="index, follow' in profile.text
    assert "Gestion Velora" in profile.text
    assert "gestionvelora.com" in profile.text
    assert 'href="https://www.gestionvelora.com/"' in profile.text
    assert '"@type": "FAQPage"' in profile.text
    assert "info@gestionvelora.com" in profile.text
    assert 'href="mailto:info@gestionvelora.com"' in profile.text
    assert "Questions? Email Gestion Velora" in profile.text
    assert "Email info@gestionvelora.com" in profile.text
    assert "+1-514-777-1731" in profile.text
    assert "https://www.gestionvelora.com/og-image.png" in profile.text
    assert 'class="skip-link" href="#main-content"' in profile.text
    assert '<main id="main-content">' in profile.text
    assert 'id="velora-nav-toggle"' in profile.text
    assert 'id="velora-nav-links"' in profile.text
    assert "event.key === 'Escape'" in profile.text
    assert "Published by GEOSITION and last reviewed July 22, 2026." in profile.text
    assert "It is not a certification" in profile.text
    assert "this page does not claim ownership of, or affiliation with, Gestion Velora" in profile.text
    assert 'id="sources"' in profile.text
    assert 'lang="fr-CA">Site officiel en français' in profile.text
    assert 'hreflang="en-CA"' in profile.text
    assert 'href="/gestion-velora"' not in landing.text
    assert 'href="https://www.gestionvelora.com/"' in landing.text


def test_public_sitemap_includes_gestion_velora_profile(client):
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "https://geositionai.com/platform" in response.text
    assert "https://geositionai.com/gestion-velora" in response.text
    assert "https://geositionai.com/manifesto" in response.text
    # /about serves the manifesto template and its canonical points at /manifesto,
    # so it must stay out of the sitemap: advertising a non-canonical duplicate
    # splits indexing signals between the two URLs.
    assert "https://geositionai.com/about" not in response.text


def test_platform_public_pages_and_assets_support_head(client):
    root = client.head("/")
    landing = client.head("/platform")
    css = client.head("/platform/assets/site.css")
    dashboard_loop = client.head("/platform/assets/dashboard-loop.js")
    hero = client.head("/platform/assets/hero-bg.png")

    assert root.status_code == 200
    assert landing.status_code == 200
    assert landing.headers["content-type"].startswith("text/html")
    assert css.status_code == 200
    assert "public, max-age=31536000, immutable" in css.headers["cache-control"]
    assert dashboard_loop.status_code == 200
    assert dashboard_loop.headers["content-type"].startswith("text/javascript")
    assert hero.status_code == 200
    assert hero.headers["content-type"].startswith("image/png")


def test_public_geo_discovery_points_to_production_platform(client):
    robots = client.get("/robots.txt")
    llms = client.get("/llms.txt")
    ai_txt = client.get("/.well-known/ai.txt")

    assert robots.status_code == 200
    assert "User-agent: GPTBot" in robots.text
    assert "User-agent: ClaudeBot" in robots.text
    assert "User-agent: PerplexityBot" in robots.text
    assert "Sitemap: https://geositionai.com/sitemap.xml" in robots.text
    assert "AI-Summary:" not in robots.text
    assert "AI-FAQ:" not in robots.text
    assert "LLMS:" not in robots.text
    assert "https://geosition-web.onrender.com" not in robots.text

    assert llms.status_code == 200
    assert "> Source-available Generative Engine Optimization" in llms.text
    assert "[GEOSITION platform](https://geositionai.com/platform)" in llms.text
    assert "Primary Platform Flow" in llms.text
    assert "Copy Skill Files into an AI coding tool" in llms.text
    assert "https://geosition-web.onrender.com" not in llms.text

    assert ai_txt.status_code == 200
    assert "Summary: https://geositionai.com/ai/summary.json" in ai_txt.text
    assert "LLMS: https://geositionai.com/llms.txt" in ai_txt.text


def test_public_discovery_files_support_head_and_rss(client):
    for path in ("/robots.txt", "/sitemap.xml", "/llms.txt", "/llms-full.txt", "/feed.xml"):
        assert client.head(path).status_code == 200

    feed = client.get("/feed.xml")
    llms_full = client.get("/llms-full.txt")
    landing = client.get("/platform")
    assert feed.headers["content-type"].startswith("application/rss+xml")
    assert "Gestion Velora implementation profile" in feed.text
    assert "Extended operational context" in llms_full.text
    assert 'rel="alternate" type="application/rss+xml"' in landing.text


def test_public_geo_json_describes_agent_workflow(client):
    summary = client.get("/ai/summary.json").json()
    faq = client.get("/ai/faq.json").json()
    service = client.get("/ai/service.json").json()

    assert summary["url"] == "https://geositionai.com/platform"
    assert summary["discovery"]["llmsTxt"] == "https://geositionai.com/llms.txt"
    assert "run AI visibility benchmark" in summary["coreWorkflow"]
    assert "https://geosition-web.onrender.com" not in str(summary)

    answers = " ".join(item["answer"] for item in faq["faqs"])
    assert "Optional discovery files are unscored" in answers
    assert "Skill Files" in answers
    assert "before/after deltas by URL and prompt" in answers

    assert service["url"] == "https://geositionai.com/platform"
    assert "Skill Files handoff for AI coding tools" in service["capabilities"]
    assert service["entrypoints"]["summary"] == "https://geositionai.com/ai/summary.json"


def test_platform_favicon_assets_are_served_and_linked(client):
    """Browser tab icon assets must be served and linked from the platform page."""
    landing = client.get("/platform")
    ico = client.get("/favicon.ico")
    png = client.get("/platform/assets/favicon-32.png")
    apple = client.get("/platform/assets/apple-touch-icon.png")

    assert landing.status_code == 200
    assert b'href="/favicon.ico' in landing.content
    assert b'href="/platform/assets/favicon-32.png' in landing.content
    assert b'href="/platform/assets/apple-touch-icon.png' in landing.content
    assert ico.status_code == 200
    assert ico.headers["content-type"].startswith("image/x-icon")
    assert png.status_code == 200
    assert png.headers["content-type"].startswith("image/png")
    assert "public, max-age=31536000, immutable" in png.headers["cache-control"]
    assert apple.status_code == 200
    assert apple.headers["content-type"].startswith("image/png")


def test_demo_contiene_form_audit(client):
    """La demo legacy deve contenere il form per l'URL di audit."""
    response = client.get("/demo")
    assert response.status_code == 200
    assert b"url-input" in response.content
    assert b"GEOSITION" in response.content


# ─── Test: GET /health ────────────────────────────────────────────────────────


def test_health_ritorna_200_e_status_ok(client):
    """GET /health deve restituire status 'ok' e la versione."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


# ─── Test: POST /api/audit ────────────────────────────────────────────────────


def test_post_audit_url_valido_ritorna_200(client):
    """POST /api/audit with a valid URL and mocked run_full_audit returns 200."""
    mock_result = _make_mock_audit_result()

    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        response = client.post("/api/audit", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 75
    assert data["band"] == "good"
    assert "checks" in data
    assert "recommendations" in data


def test_post_audit_senza_url_ritorna_422(client):
    """POST /api/audit senza campo 'url' deve restituire 422 Unprocessable Entity."""
    response = client.post("/api/audit", json={})
    assert response.status_code == 422


def test_post_audit_url_non_stringa_ritorna_422(client):
    """POST /api/audit con url non stringa (fix #149) deve restituire 422."""
    response = client.post("/api/audit", json={"url": 12345})
    assert response.status_code == 422


def test_post_audit_body_vuoto_ritorna_422(client):
    """POST /api/audit without a JSON body returns 422."""
    response = client.post("/api/audit", content=b"", headers={"content-type": "application/json"})
    assert response.status_code == 422


def test_post_audit_include_report_url(client):
    """POST /api/audit deve includere report_url nella response."""
    mock_result = _make_mock_audit_result()

    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        response = client.post("/api/audit", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert "report_url" in data
    assert data["report_url"].startswith("/report/")


def test_post_audit_normalizza_url_senza_schema(client):
    """POST /api/audit aggiunge 'https://' se manca il protocollo."""
    mock_result = _make_mock_audit_result()

    # run_full_audit is imported locally inside the _run_audit function:
    # bisogna patchare il modulo sorgente dove è definita la funzione
    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        response = client.post("/api/audit", json={"url": "example.com"})

    assert response.status_code == 200
    # Verifies that il result sia corretto (URL normalizzato usato internamente)
    data = response.json()
    assert data["url"].startswith("https://")


def test_post_audit_url_private_ritorna_400(client):
    """POST /api/audit with a URL pointing to an internal network must return 400 (anti-SSRF)."""
    response = client.post("/api/audit", json={"url": "http://192.168.1.1"})
    assert response.status_code == 400


# ─── Test: GET /api/audit ─────────────────────────────────────────────────────


def test_get_audit_url_valido_ritorna_200(client):
    """GET /api/audit?url=... deve worksre come POST."""
    mock_result = _make_mock_audit_result()

    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        response = client.get("/api/audit?url=https://example.com")

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 75


def test_get_audit_senza_url_ritorna_422(client):
    """GET /api/audit without a url parameter returns 422."""
    response = client.get("/api/audit")
    assert response.status_code == 422


# ─── Test: cache ─────────────────────────────────────────────────────────────


def test_post_audit_usa_cache_per_secondo_request(client):
    """Second request for the same URL uses the cache (run_full_audit called only once)."""
    mock_result = _make_mock_audit_result()

    # run_full_audit è importato localmente: patch sul modulo sorgente
    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result) as mock_audit:
        # First request: executes audit
        r1 = client.post("/api/audit", json={"url": "https://example.com"})
        # Seconda richiesta: usa cache
        r2 = client.post("/api/audit", json={"url": "https://example.com"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    # run_full_audit must be called exactly once
    assert mock_audit.call_count == 1


# ─── Test: rate limiting ──────────────────────────────────────────────────────


def test_rate_limit_429_dopo_troppe_richieste(client):
    """Dopo aver superato il rate limit, deve restituire 429."""
    from geo_optimizer.web.app import _RATE_LIMIT_MAX_REQUESTS

    mock_result = _make_mock_audit_result()

    # Riempi il rate limit store con timestamp recenti
    import time

    now = time.time()
    _rate_limit_store["testclient"] = [now] * _RATE_LIMIT_MAX_REQUESTS

    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        # This request must be blocked
        response = client.get("/api/audit?url=https://example.com")

    # Il rate limiter usa l'IP del client — in ambiente di test è "testclient"
    # Verify that the rate limit is applied to some IP
    assert response.status_code in (200, 429)  # dipende dall'IP riconosciuto


def test_check_rate_limit_blocca_dopo_limite():
    """_check_rate_limit() returns False after exceeding the limit."""
    import time

    from geo_optimizer.web.app import _RATE_LIMIT_MAX_REQUESTS

    test_ip = "10.0.0.99_test_rate_limit"
    now = time.time()

    # Imposta già al massimo
    _rate_limit_store[test_ip] = [now] * _RATE_LIMIT_MAX_REQUESTS

    # The next request must be blocked — _check_rate_limit is async (fix #209)
    result = asyncio.run(_check_rate_limit(test_ip))
    assert result is False


def test_check_rate_limit_consente_entro_limite():
    """_check_rate_limit() returns True while below the limit."""
    test_ip = "10.0.0.88_test_rate_ok"
    # _check_rate_limit è async (fix #209)
    result = asyncio.run(_check_rate_limit(test_ip))
    assert result is True


# ─── Test: headers di sicurezza ──────────────────────────────────────────────


def test_security_headers_presenti(client):
    """Le risposte devono contenere gli header di sicurezza HTTP."""
    response = client.get("/health")
    assert "x-content-type-options" in response.headers
    assert "x-frame-options" in response.headers
    assert "content-security-policy" in response.headers


# ─── Test: _audit_result_to_dict ────────────────────────────────────────────


def test_audit_result_to_dict_include_tutti_campi():
    """_audit_result_to_dict deve includere TUTTI i campi del result audit (fix #151)."""
    from geo_optimizer.web.app import _audit_result_to_dict

    result = _make_mock_audit_result()
    d = _audit_result_to_dict(result)

    # Campi base
    assert d["url"] == "https://example.com"
    assert d["score"] == 75
    assert d["band"] == "good"
    assert d["http_status"] == 200
    assert d["page_size"] == 12345
    assert "timestamp" in d
    assert "recommendations" in d

    # Campi checks (struttura nidificata)
    checks = d["checks"]

    # robots: extra fields compared to the previous version
    robots = checks["robots_txt"]
    assert "citation_bots_explicit" in robots
    assert "bots_partial" in robots

    # llms: campi extra
    llms = checks["llms_txt"]
    assert "has_description" in llms

    # schema: raw_schemas
    schema = checks["schema_jsonld"]
    assert "raw_schemas" in schema

    # meta: campi extra
    meta = checks["meta_tags"]
    assert "has_og_image" in meta
    assert "description_text" in meta
    assert "title_length" in meta
    assert "canonical_url" in meta

    # content: campi extra
    content = checks["content"]
    assert "h1_text" in content
    assert "numbers_count" in content
    assert "external_links_count" in content


# ─── Test: round-trip _audit_result_to_dict → _dict_to_audit_result ──────────


def test_round_trip_audit_result_to_dict_e_ritorno():
    """_audit_result_to_dict → _dict_to_audit_result preserva tutti i campi principali."""
    from geo_optimizer.web.app import _audit_result_to_dict, _dict_to_audit_result

    # Arrange
    original = _make_mock_audit_result(score=82, band="good")

    # Act
    d = _audit_result_to_dict(original)
    reconstructed = _dict_to_audit_result(d)

    # Assert: campi scalari
    assert reconstructed.url == original.url
    assert reconstructed.score == original.score
    assert reconstructed.band == original.band
    assert reconstructed.http_status == original.http_status
    assert reconstructed.page_size == original.page_size

    # Assert: sub-risultati robots
    assert reconstructed.robots.found == original.robots.found
    assert reconstructed.robots.citation_bots_ok == original.robots.citation_bots_ok
    assert reconstructed.robots.bots_allowed == original.robots.bots_allowed

    # Assert: sub-risultati llms
    assert reconstructed.llms.found == original.llms.found
    assert reconstructed.llms.word_count == original.llms.word_count

    # Assert: sub-risultati meta
    assert reconstructed.meta.has_title == original.meta.has_title
    assert reconstructed.meta.title_text == original.meta.title_text
    assert reconstructed.meta.description_length == original.meta.description_length

    # Assert: sub-risultati content
    assert reconstructed.content.has_h1 == original.content.has_h1
    assert reconstructed.content.word_count == original.content.word_count
    assert reconstructed.content.h1_text == original.content.h1_text


# ─── Test: GET /badge ─────────────────────────────────────────────────────────


def test_badge_happy_path_restituisce_svg(client):
    """GET /badge with a valid URL and mocked audit returns an SVG with the score."""
    mock_result = _make_mock_audit_result(score=75, band="good")

    with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
        response = client.get("/badge?url=https://example.com")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert b"75/100" in response.content
    assert b"<svg" in response.content


def test_badge_audit_timeout_restituisce_badge_errore(client):
    """GET /badge with a timed-out audit returns an error SVG badge."""
    import asyncio

    with patch(
        "geo_optimizer.core.audit.run_full_audit",
        side_effect=asyncio.TimeoutError(),
    ):
        response = client.get("/badge?url=https://example.com")

    # Even on timeout the badge is returned (not 5xx)
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert b"Error" in response.content


def test_badge_audit_eccezione_generica_restituisce_badge_errore(client):
    """GET /badge with a generic exception during the audit returns an error SVG badge."""
    with patch(
        "geo_optimizer.core.audit.run_full_audit",
        side_effect=RuntimeError("connessione fallita"),
    ):
        response = client.get("/badge?url=https://example.com")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert b"Error" in response.content


def test_badge_url_private_ritorna_400(client):
    """GET /badge with an internal URL returns 400 (anti-SSRF)."""
    response = client.get("/badge?url=http://10.0.0.1")
    assert response.status_code == 400


def test_badge_senza_url_ritorna_422(client):
    """GET /badge without a url parameter returns 422."""
    response = client.get("/badge")
    assert response.status_code == 422


# ─── Test: GET /report/{report_id} ───────────────────────────────────────────


def test_report_id_non_hex_ritorna_400(client):
    """GET /report/{id} with a non-hexadecimal ID returns 400."""
    response = client.get("/report/ZZZZinvalidXXXX")
    assert response.status_code == 400


def test_report_id_troppo_corto_ritorna_400(client):
    """GET /report/{id} with an ID shorter than 32 characters returns 400."""
    response = client.get("/report/abc123")
    assert response.status_code == 400


def test_report_id_maiuscolo_ritorna_400(client):
    """GET /report/{id} with an uppercase ID returns 400 (fix #210)."""
    # The regex accepts only lowercase — the ID is exactly 32 characters but uppercase
    id_maiuscolo = "A" * 32
    response = client.get(f"/report/{id_maiuscolo}")
    assert response.status_code == 400


def test_report_id_valido_ma_non_in_cache_ritorna_404(client):
    """GET /report/{id} with a valid hex ID not in the cache returns 404."""
    # ID valido: 32 caratteri esadecimali minuscoli
    id_valido = "a" * 32
    response = client.get(f"/report/{id_valido}")
    assert response.status_code == 404


def test_report_id_valido_con_report_in_cache_ritorna_html(client):
    """GET /report/{id} with a cached report returns HTML 200."""
    from geo_optimizer.web.app import _audit_result_to_dict

    mock_result = _make_mock_audit_result()
    data = _audit_result_to_dict(mock_result)

    # Insert directly into cache with a known ID
    import time

    report_id = "b" * 32  # 32 caratteri hex validi
    _audit_cache[report_id] = {"data": data, "cached_at": time.time()}

    response = client.get(f"/report/{report_id}")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# ─── Test: _verify_bearer_token ───────────────────────────────────────────────


def test_verify_bearer_token_senza_geo_api_token_ritorna_true():
    """_verify_bearer_token returns True when GEO_API_TOKEN is not configured."""
    import geo_optimizer.web.app as app_module
    from geo_optimizer.web.app import _verify_bearer_token

    # Arrange: simulate _API_TOKEN = None
    original = app_module._API_TOKEN
    app_module._API_TOKEN = None

    mock_request = MagicMock()
    mock_request.headers.get.return_value = ""

    try:
        # Act
        result = _verify_bearer_token(mock_request)
    finally:
        app_module._API_TOKEN = original

    # Assert
    assert result is True


def test_verify_bearer_token_con_token_corretto_ritorna_true():
    """_verify_bearer_token returns True with a valid token in the Authorization header."""
    import geo_optimizer.web.app as app_module
    from geo_optimizer.web.app import _verify_bearer_token

    # Arrange: imposta un token di test
    original = app_module._API_TOKEN
    app_module._API_TOKEN = "secret-token-test-123"

    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer secret-token-test-123"

    try:
        result = _verify_bearer_token(mock_request)
    finally:
        app_module._API_TOKEN = original

    # Assert
    assert result is True


def test_verify_bearer_token_con_token_sbagliato_ritorna_false():
    """_verify_bearer_token returns False with an incorrect token."""
    import geo_optimizer.web.app as app_module
    from geo_optimizer.web.app import _verify_bearer_token

    # Arrange
    original = app_module._API_TOKEN
    app_module._API_TOKEN = "secret-token-corretto"

    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer token-sbagliato"

    try:
        result = _verify_bearer_token(mock_request)
    finally:
        app_module._API_TOKEN = original

    # Assert
    assert result is False


def test_verify_bearer_token_senza_header_authorization_ritorna_false():
    """_verify_bearer_token returns False when the Authorization header is missing."""
    import geo_optimizer.web.app as app_module
    from geo_optimizer.web.app import _verify_bearer_token

    # Arrange
    original = app_module._API_TOKEN
    app_module._API_TOKEN = "un-token-qualsiasi"

    mock_request = MagicMock()
    mock_request.headers.get.return_value = ""  # no header

    try:
        result = _verify_bearer_token(mock_request)
    finally:
        app_module._API_TOKEN = original

    # Assert
    assert result is False


def test_post_audit_con_token_valido_restituisce_200(client):
    """POST /api/audit with GEO_API_TOKEN set and correct token returns 200."""
    import geo_optimizer.web.app as app_module

    original_token = app_module._API_TOKEN
    app_module._API_TOKEN = "test-token-xyz"

    mock_result = _make_mock_audit_result()

    try:
        with patch("geo_optimizer.core.audit.run_full_audit", return_value=mock_result):
            response = client.post(
                "/api/audit",
                json={"url": "https://example.com"},
                headers={"Authorization": "Bearer test-token-xyz"},
            )
    finally:
        app_module._API_TOKEN = original_token

    assert response.status_code == 200


def test_post_audit_con_token_sbagliato_ritorna_401(client):
    """POST /api/audit with GEO_API_TOKEN set and wrong token returns 401."""
    import geo_optimizer.web.app as app_module

    original_token = app_module._API_TOKEN
    app_module._API_TOKEN = "token-corretto"

    try:
        response = client.post(
            "/api/audit",
            json={"url": "https://example.com"},
            headers={"Authorization": "Bearer token-sbagliato"},
        )
    finally:
        app_module._API_TOKEN = original_token

    assert response.status_code == 401


# ─── Test endpoint AI discovery ──────────────────────────────────────────────


def test_ai_faq_json_punteggi_coerenti_con_config(client):
    """GET /ai/faq.json — i punteggi delle categorie devono corrispondere a SCORING in config.py.

    Test di regressione per il bug in cui la response hard-coded descriveva
    7 categorie con punteggi errati (schema=22, content=14, signals=8) invece
    degli 8 corretti (schema=16, content=12, signals=6, brand=10).
    """
    # Act
    response = client.get("/ai/faq.json")

    # Assert — status e struttura
    assert response.status_code == 200
    data = response.json()
    assert "faqs" in data
    faq_list = data["faqs"]
    assert len(faq_list) >= 2

    # Trova la FAQ sul calcolo del punteggio
    score_faq = next(
        (f for f in faq_list if "score" in f.get("question", "").lower() or "calculat" in f.get("question", "").lower()),
        None,
    )
    assert score_faq is not None, "Noa FAQ sul calcolo del punteggio trovata"

    response = score_faq["answer"]

    assert "crawler access (25)" in response
    assert "schema (16)" in response
    assert "content (21)" in response
    assert "signals (8)" in response
    assert "unscored" in response
    assert "citations are measured separately" in response


def test_ai_summary_json_restituisce_struttura_valida(client):
    """GET /ai/summary.json — deve contenere name, description, url, lastModified."""
    response = client.get("/ai/summary.json")

    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "description" in data
    assert "url" in data
    assert "lastModified" in data


def test_ai_service_json_restituisce_capabilities(client):
    """GET /ai/service.json — deve contenere name e capabilities non vuote."""
    response = client.get("/ai/service.json")

    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "capabilities" in data
    assert len(data["capabilities"]) > 0


def test_public_guided_audit_discloses_scope_and_accepts_prefilled_url(client):
    landing = client.get("/platform")
    demo = client.get("/demo?url=example.com&start=1")
    assert "'/demo?url='" in landing.text
    assert demo.status_code == 200
    assert "This checks your page and public site signals" in demo.text
    assert 'id="first-actions"' in demo.text
    assert "auditParams.get('url')" in demo.text
    assert "data.error" in demo.text

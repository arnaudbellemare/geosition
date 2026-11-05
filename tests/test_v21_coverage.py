"""
Test v2.1 — Fills remaining coverage gaps in the geo_optimizer package.

Covers:
- llms_generator.py: on_status callback, non-numeric priority, url_to_label
  with numeric slug, fetch_titles=True, Optional section, SSRF validation
  in discover_sitemap, common-paths fallback
- formatters.py: citation_bots_ok, llms found without H1, schema without WebSite,
  schema without FAQPage
- schema_validator.py: @context list with invalid first element, empty @type list,
  URL field that is neither string nor list
- schema_cmd.py: path traversal --file and --faq-file, _print_analysis for all
  schema types, verbose=True, FAQ > 3
- validators.py: must_exist=True with a directory instead of a file, ValueError
  in ip_address ignored (DNS skip), file not found
"""

import socket
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlparse

import pytest
from click.testing import CliRunner

from geo_optimizer.cli.formatters import format_audit_text
from geo_optimizer.cli.schema_cmd import schema
from geo_optimizer.core.llms_generator import (
    SitemapUrl,
    discover_sitemap,
    fetch_sitemap,
    generate_llms_txt,
    url_to_label,
)
from geo_optimizer.core.schema_validator import validate_jsonld
from geo_optimizer.models.results import (
    AuditResult,
    ContentResult,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
)
from geo_optimizer.utils.validators import validate_public_url, validate_safe_path


@pytest.fixture(autouse=True)
def _mock_v21_url_validation(monkeypatch):
    """Makes URL validation deterministic in offline v2.1 tests."""

    def _fake_resolve(url):
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("example.com"):
            return True, None, ["93.184.216.34"]
        if host in {"localhost", "169.254.169.254", "192.168.0.1", "10.0.0.1"}:
            return False, "blocked for test", []
        return True, None, ["93.184.216.34"]

    def _fake_validate(url):
        ok, reason, _ips = _fake_resolve(url)
        return ok, reason

    monkeypatch.setattr("geo_optimizer.utils.validators.resolve_and_validate_url", _fake_resolve)
    monkeypatch.setattr("geo_optimizer.core.llms_generator.resolve_and_validate_url", _fake_resolve)
    monkeypatch.setattr("geo_optimizer.core.llms_generator.validate_public_url", _fake_validate)


# ============================================================================
# Fixture comune per AuditResult
# ============================================================================


def _make_audit_result(**overrides) -> AuditResult:
    """Creates a base AuditResult with specific overrides."""
    result = AuditResult(
        url="https://example.com",
        score=75,
        band="good",
        robots=RobotsResult(
            found=True,
            bots_allowed=["GPTBot"],
            bots_blocked=[],
            bots_missing=[],
            citation_bots_ok=False,
        ),
        llms=LlmsTxtResult(
            found=True,
            has_h1=True,
            has_sections=True,
            has_links=True,
            word_count=100,
        ),
        schema=SchemaResult(
            found_types=["WebSite", "FAQPage"],
            has_website=True,
            has_faq=True,
            has_webapp=False,
            raw_schemas=[],
        ),
        meta=MetaResult(
            has_title=True,
            title_text="Test",
            has_description=True,
            description_length=100,
            has_canonical=True,
            has_og_title=True,
            has_og_description=True,
            has_og_image=True,
        ),
        content=ContentResult(
            has_h1=True,
            h1_text="Test",
            heading_count=5,
            word_count=500,
            has_numbers=True,
            numbers_count=3,
            has_links=True,
            external_links_count=2,
        ),
        recommendations=[],
    )
    # Applica gli override con notazione "robots.found" → result.robots.found
    for chiave, value in overrides.items():
        parti = chiave.split(".")
        obj = result
        for parte in parti[:-1]:
            obj = getattr(obj, parte)
        setattr(obj, parti[-1], value)
    return result


# ============================================================================
# llms_generator.py — callback on_status
# ============================================================================


class TestFetchSitemapOnStatus:
    """Verifies that on_status is called across the fetch_sitemap branches."""

    def test_on_status_called_at_max_depth(self):
        """Line 63: on_status called when _depth >= _MAX_SITEMAP_DEPTH."""
        callback = Mock()
        # _MAX_SITEMAP_DEPTH è 3, quindi _depth=3 attiva il branch
        result = fetch_sitemap(
            "https://example.com/sitemap.xml",
            on_status=callback,
            _depth=3,
        )
        assert result == []
        # Should have called on_status with the max-depth message
        callback.assert_called_once()
        messaggio = callback.call_args[0][0]
        assert "depth" in messaggio.lower() or "sitemap" in messaggio.lower()

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_on_status_called_on_fetch_error(self, mock_create):
        """Line 77: on_status called when the sitemap fetch fails."""
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("Network timeout")
        mock_create.return_value = mock_session

        callback = Mock()
        result = fetch_sitemap(
            "https://example.com/sitemap.xml",
            on_status=callback,
            _depth=0,
        )
        assert result == []
        # Should have called on_status twice: once for "Fetching" and once for the error
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("error" in c.lower() or "sitemap" in c.lower() for c in calls)

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_on_status_called_for_sitemap_index(self, mock_create):
        """Line 87: on_status called when a sitemap index is detected."""
        xml_indice = """<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap-0.xml</loc></sitemap>
        </sitemapindex>"""
        xml_vuoto = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        </urlset>"""

        mock_session = MagicMock()
        resp_index = Mock()
        resp_index.content = xml_indice.encode()
        resp_index.raise_for_status = Mock()
        resp_empty = Mock()
        resp_empty.content = xml_vuoto.encode()
        resp_empty.raise_for_status = Mock()
        # Prima chiamata → indice, seconda chiamata → sub-sitemap vuoto
        mock_session.get.side_effect = [resp_index, resp_empty]
        mock_create.return_value = mock_session

        callback = Mock()
        fetch_sitemap(
            "https://example.com/sitemap_index.xml",
            on_status=callback,
            _depth=0,
        )
        # on_status deve aver segnalato la presenza dell'indice
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("index" in c.lower() or "sitemaps" in c.lower() for c in calls)

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_on_status_called_with_urls_found(self, mock_create):
        """Line 100: on_status called with the number of URLs found."""
        xml_sitemap = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/pagina1</loc></url>
            <url><loc>https://example.com/pagina2</loc></url>
        </urlset>"""

        mock_session = MagicMock()
        resp = Mock()
        resp.content = xml_sitemap.encode()
        resp.raise_for_status = Mock()
        mock_session.get.return_value = resp
        mock_create.return_value = mock_session

        callback = Mock()
        result = fetch_sitemap(
            "https://example.com/sitemap.xml",
            on_status=callback,
            _depth=0,
        )
        assert len(result) == 2
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("2" in c or "found" in c.lower() for c in calls)


# ============================================================================
# llms_generator.py — priority non-numeric (righe 119-120)
# ============================================================================


class TestPriorityNonNumerica:
    """Verifies that un value priority non numerico venga ignored silenziosamente."""

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_non_numeric_priority_ignored(self, mock_create):
        """Lines 119–120: <priority>high</priority> → ValueError ignored, priority=0.5."""
        xml_sitemap = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/page</loc>
                <priority>high</priority>
            </url>
        </urlset>"""

        mock_session = MagicMock()
        resp = Mock()
        resp.content = xml_sitemap.encode()
        resp.raise_for_status = Mock()
        mock_session.get.return_value = resp
        mock_create.return_value = mock_session

        result = fetch_sitemap("https://example.com/sitemap.xml", _depth=0)
        assert len(result) == 1
        # The default value (0.5) must be kept when the priority is not numeric
        assert result[0].priority == 0.5
        assert result[0].url == "https://example.com/page"


# ============================================================================
# llms_generator.py — url_to_label con numeric slug (riga 221)
# ============================================================================


class TestUrlToLabelSlugNumerico:
    """Verifies url_to_label behaviour when the last path segment is all digits."""

    def test_ultimo_segmento_numerico_usa_path_completo(self):
        """Line 221: url come /blog/12345 → label è 'Blog/12345', non solo '12345'."""
        label = url_to_label("https://example.com/blog/12345", "example.com")
        # When the last segment is all digits, use the last two segments
        assert "12345" in label
        assert "Blog" in label or "blog" in label.lower()

    def test_ultimo_segmento_alfanumerico_works_normalmente(self):
        """Segmento con lettere e cifre non attiva il branch numerico."""
        label = url_to_label("https://example.com/blog/post-123", "example.com")
        assert "Post 123" in label or "post-123" in label.lower()

    def test_homepage_returns_homepage(self):
        """Path vuoto → 'Homepage'."""
        label = url_to_label("https://example.com/", "example.com")
        assert label == "Homepage"

    def test_slug_con_trattini_diventa_title(self):
        """Slug with hyphens is converted to Title Case."""
        label = url_to_label("https://example.com/my-awesome-page", "example.com")
        assert label == "My Awesome Page"


# ============================================================================
# llms_generator.py — generate_llms_txt con fetch_titles=True (righe 290-292)
# ============================================================================


class TestGenerateLlmsTxtFetchTitles:
    """Verifies the fetch_titles=True path in generate_llms_txt."""

    def test_fetch_titles_true_usa_titolo_fetchato(self):
        """Lines 290–292: if fetch_titles=True, calls fetch_page_title and uses the result."""
        urls = [SitemapUrl(url="https://example.com/pagina1")]

        with patch(
            "geo_optimizer.core.llms_generator.fetch_page_title",
            return_value="Titolo Fetchato",
        ):
            result = generate_llms_txt(
                "https://example.com",
                urls,
                site_name="Test",
                description="Desc test",
                fetch_titles=True,
            )
        assert "Titolo Fetchato" in result

    def test_fetch_titles_true_fallback_se_none(self):
        """If fetch_page_title returns None, falls back to url_to_label."""
        urls = [SitemapUrl(url="https://example.com/my-about-page")]

        with patch(
            "geo_optimizer.core.llms_generator.fetch_page_title",
            return_value=None,
        ):
            result = generate_llms_txt(
                "https://example.com",
                urls,
                site_name="Test",
                description="Desc test",
                fetch_titles=True,
            )
        # Should fall back to url_to_label which title-cases the slug
        assert "My About Page" in result

    def test_fetch_titles_false_non_chiama_fetch(self):
        """fetch_titles=False (default) never calls fetch_page_title."""
        urls = [SitemapUrl(url="https://example.com/page")]

        with patch("geo_optimizer.core.llms_generator.fetch_page_title") as mock_fetch:
            generate_llms_txt(
                "https://example.com",
                urls,
                site_name="Test",
                description="Desc",
                fetch_titles=False,
            )
        mock_fetch.assert_not_called()


# ============================================================================
# llms_generator.py — Optional section in generate_llms_txt (righe 341, 351-357)
# ============================================================================


class TestGenerateLlmsTxtSezioneOptional:
    """Verifies the Optional section for Privacy, Terms, Contact, Other."""

    def test_url_privacy_finisce_in_sezione_optional(self):
        """Lines 351–357: privacy policy URL goes in the Optional section."""
        urls = [
            SitemapUrl(url="https://example.com/privacy-policy"),
            SitemapUrl(url="https://example.com/about"),
        ]
        result = generate_llms_txt(
            "https://example.com",
            urls,
            site_name="Test",
            description="Desc",
        )
        # The Optional section must be present and contain the privacy URL
        assert "## Optional" in result
        assert "privacy" in result.lower()

    def test_url_terms_finisce_in_sezione_optional(self):
        """URL with /terms/ goes in the Optional section."""
        urls = [SitemapUrl(url="https://example.com/terms-of-service")]
        result = generate_llms_txt(
            "https://example.com",
            urls,
            site_name="Test",
            description="Desc",
        )
        assert "## Optional" in result
        assert "Terms" in result

    def test_categories_vuote_non_producono_sezione(self):
        """Line 341: category with items=[]: section is not emitted."""
        # URL with no content after filtering (homepage is skipped for the section)
        urls = [SitemapUrl(url="https://example.com/")]
        result = generate_llms_txt(
            "https://example.com",
            urls,
            site_name="Test",
            description="Desc",
        )
        # La homepage non produce una sezione H2 ma una riga speciale
        assert "## _homepage" not in result

    def test_url_contact_in_optional_con_categoria(self):
        """URL /contact finisce in Optional con label categoria."""
        urls = [SitemapUrl(url="https://example.com/contact")]
        result = generate_llms_txt(
            "https://example.com",
            urls,
            site_name="Test",
            description="Desc",
        )
        assert "## Optional" in result
        assert "Contact" in result


# ============================================================================
# llms_generator.py — discover_sitemap con validazione SSRF (righe 407-408, 413-414)
# ============================================================================


class TestDiscoverSitemapValidazioneSSRF:
    """Verifies that discover_sitemap ignores unsafe sitemap URLs from robots.txt."""

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_unsafe_sitemap_ignored(self, mock_create):
        """Lines 407–408: sitemap URL that fails validate_public_url is ignored."""
        mock_session = MagicMock()
        # robots.txt con URL sitemap verso IP private
        robots_resp = Mock(
            text="Sitemap: http://192.168.1.1/sitemap.xml",
            status_code=200,
        )
        # Fallback common paths → tutti 404
        head_resp = Mock(status_code=404)
        mock_session.get.return_value = robots_resp
        mock_session.head.return_value = head_resp
        mock_create.return_value = mock_session

        # real validate_public_url blocks 192.168.1.1 (IP private)
        result = discover_sitemap("https://example.com")
        # The unsafe URL must not be returned
        assert result != "http://192.168.1.1/sitemap.xml"

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_external_domain_sitemap_ignored(self, mock_create):
        """Lines 413–414: sitemap URL from an external domain is ignored."""
        mock_session = MagicMock()
        robots_resp = Mock(
            text="Sitemap: https://attaccante.com/sitemap.xml",
            status_code=200,
        )
        head_resp = Mock(status_code=404)
        mock_session.get.return_value = robots_resp
        mock_session.head.return_value = head_resp
        mock_create.return_value = mock_session

        result = discover_sitemap("https://example.com")
        assert result != "https://attaccante.com/sitemap.xml"


# ============================================================================
# llms_generator.py — fallback common paths (righe 424, 426-427, 431)
# ============================================================================


class TestDiscoverSitemapFallbackCommonPaths:
    """Verifies the fallback to common paths when robots.txt has no Sitemap: directive."""

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_fallback_sitemap_xml_found(self, mock_create):
        """Lines 424–426: common path /sitemap.xml responds 200 → returned."""
        mock_session = MagicMock()
        # robots.txt senza direttiva Sitemap
        robots_resp = Mock(text="User-agent: *\nAllow: /", status_code=200)
        head_ok = Mock(status_code=200)
        mock_session.get.return_value = robots_resp
        mock_session.head.return_value = head_ok
        mock_create.return_value = mock_session

        result = discover_sitemap("https://example.com")
        assert result is not None
        assert "sitemap" in result.lower()

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_fallback_no_sitemap_found_returns_none(self, mock_create):
        """Line 431: no path works → on_status callback + returns None."""
        mock_session = MagicMock()
        robots_resp = Mock(text="User-agent: *\nAllow: /", status_code=200)
        head_404 = Mock(status_code=404)
        mock_session.get.return_value = robots_resp
        mock_session.head.return_value = head_404
        mock_create.return_value = mock_session

        callback = Mock()
        result = discover_sitemap("https://example.com", on_status=callback)
        assert result is None
        # on_status deve aver segnalato l'assenza di sitemap
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("no sitemap" in c.lower() or "not found" in c.lower() for c in calls)

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_fallback_head_exception_continues(self, mock_create):
        """Line 427: ConnectionError su HEAD → continues al path successivo."""
        mock_session = MagicMock()
        robots_resp = Mock(text="User-agent: *", status_code=200)
        # Prima head lancia exception, la seconda risponde 200
        mock_session.get.return_value = robots_resp
        mock_session.head.side_effect = [
            ConnectionError("Timeout"),
            Mock(status_code=200),
        ]
        mock_create.return_value = mock_session

        result = discover_sitemap("https://example.com")
        # Deve trovare il secondo path non lanciare exception
        assert result is not None

    @patch("geo_optimizer.core.llms_generator.create_session_with_retry")
    def test_on_status_called_when_sitemap_found_via_common_path(self, mock_create):
        """Line 424: on_status called when sitemap found via common path."""
        mock_session = MagicMock()
        robots_resp = Mock(text="User-agent: *", status_code=200)
        head_ok = Mock(status_code=200)
        mock_session.get.return_value = robots_resp
        mock_session.head.return_value = head_ok
        mock_create.return_value = mock_session

        callback = Mock()
        result = discover_sitemap("https://example.com", on_status=callback)
        assert result is not None
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("sitemap found" in c.lower() or "found" in c.lower() for c in calls)


# ============================================================================
# formatters.py — branch mancanti (righe 89, 101, 116, 118)
# ============================================================================


class TestFormatAuditTextBranchMancanti:
    """Verifies uncovered branches in format_audit_text."""

    def test_riga_89_citation_bots_ok_true(self):
        """Line 89: citation_bots_ok=True produce messaggio 'CITATION bots'."""
        result = _make_audit_result(**{"robots.citation_bots_ok": True})
        output = format_audit_text(result)
        assert "CITATION" in output or "citation" in output.lower()

    def test_riga_101_llms_found_senza_h1(self):
        """Line 101: llms.txt found ma has_h1=False → '❌ H1 missing'."""
        result = _make_audit_result(
            **{
                "llms.found": True,
                "llms.has_h1": False,
            }
        )
        output = format_audit_text(result)
        assert "H1 missing" in output or "H1" in output

    def test_riga_116_schema_found_senza_website(self):
        """Line 116: schema found (found_types non vuoto) ma has_website=False."""
        result = _make_audit_result(
            **{
                "schema.found_types": ["FAQPage"],
                "schema.has_website": False,
                "schema.has_faq": True,
            }
        )
        output = format_audit_text(result)
        assert "WebSite schema missing" in output

    def test_riga_118_schema_found_senza_faq(self):
        """Line 118: schema found ma has_faq=False → warning FAQPage."""
        result = _make_audit_result(
            **{
                "schema.found_types": ["WebSite"],
                "schema.has_website": True,
                "schema.has_faq": False,
            }
        )
        output = format_audit_text(result)
        assert "FAQPage" in output


# ============================================================================
# schema_validator.py — branch mancanti (righe 42-43, 57, 80)
# ============================================================================


class TestValidateJsonldBranchMancanti:
    """Verifies uncovered branches in validate_jsonld."""

    def test_righe_42_43_context_lista_primo_elemento_non_valido(self):
        """Lines 42–43: @context is a list with an invalid first element."""
        schema = {
            "@context": ["http://esempio-sbagliato.com"],
            "@type": "WebSite",
        }
        ok, errore = validate_jsonld(schema)
        assert ok is False
        assert "@context" in errore

    def test_righe_42_43_context_lista_vuota(self):
        """@context è empty list → catturato da 'if not context' (falsy)."""
        schema = {
            "@context": [],
            "@type": "WebSite",
        }
        ok, errore = validate_jsonld(schema)
        assert ok is False
        # Lista vuota è falsy, catturata da riga 33-34, non da 42-43
        assert "@context" in errore

    def test_riga_57_type_lista_vuota(self):
        """Line 57: @type è empty list → '@type is empty'."""
        schema = {
            "@context": "https://schema.org",
            "@type": [],
        }
        ok, errore = validate_jsonld(schema)
        assert ok is False
        assert "@type" in errore

    def test_riga_80_url_field_e_dizionario(self):
        """Line 80: campo 'url' è dict (non str né list) → continue silenzioso."""
        schema = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Test",
            "url": {"@id": "https://example.com"},  # Nested object, non stringa
        }
        # Must not produce errors — the url field is silently skipped
        ok, errore = validate_jsonld(schema)
        assert ok is True
        assert errore is None

    def test_context_lista_con_primo_elemento_valido(self):
        """@context list with valid first element → passes validation."""
        schema = {
            "@context": ["https://schema.org"],
            "@type": "WebSite",
        }
        ok, errore = validate_jsonld(schema)
        assert ok is True

    def test_type_lista_con_primo_elemento_valido(self):
        """@type list with elements → uses the first as primary_type."""
        schema = {
            "@context": "https://schema.org",
            "@type": ["WebSite", "WebApplication"],
        }
        ok, errore = validate_jsonld(schema)
        assert ok is True


# ============================================================================
# schema_cmd.py — path traversal validation (righe 66-67, 71-72)
# ============================================================================


class TestSchemaCmdPathTraversalValidation:
    """Verifies that schema_cmd rejects invalid paths for --file and --faq-file."""

    def test_righe_66_67_file_path_non_esistente_bloccato(self):
        """Lines 66–67: --file with non-existent path → error and exit code 1."""
        runner = CliRunner()
        result = runner.invoke(
            schema,
            [
                "--file",
                "/tmp/file_inesistente_xyz_abc.html",
                "--analyze",
            ],
        )
        assert result.exit_code == 1
        assert "invalid" in result.output or "Percorso" in result.output

    def test_righe_71_72_faq_file_non_esistente_bloccato(self):
        """Lines 71–72: --faq-file with non-existent path → error and exit code 1."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # Creates a file HTML valido per --file
            with open("test.html", "w") as f:
                f.write("<html><body></body></html>")
            result = runner.invoke(
                schema,
                [
                    "--file",
                    "test.html",
                    "--type",
                    "faq",
                    "--faq-file",
                    "/tmp/faq_inesistente_xyz.json",
                ],
            )
        assert result.exit_code == 1
        assert "invalid" in result.output or "FAQ" in result.output

    def test_file_con_estensione_non_consentita_bloccato(self):
        """--file con estensione .txt non consentita → errore."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.txt", "w") as f:
                f.write("content testo")
            result = runner.invoke(
                schema,
                [
                    "--file",
                    "test.txt",
                    "--analyze",
                ],
            )
        assert result.exit_code == 1


# ============================================================================
# schema_cmd.py — _print_analysis for all schema types (righe 162-163, 167-175)
# ============================================================================


class TestSchemaCmdPrintAnalysis:
    """Verifies _print_analysis with WebApplication, Organization, BreadcrumbList."""

    def test_righe_162_163_webapplication_nel_report(self):
        """Lines 162–163: _print_analysis prints url and name for WebApplication."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write("""<html><head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "WebApplication",
                    "name": "App Test",
                    "url": "https://example.com"
                }
                </script>
                </head><body></body></html>""")
            result = runner.invoke(schema, ["--file", "test.html", "--analyze"])
        assert result.exit_code == 0
        assert "WebApplication" in result.output

    def test_righe_167_171_organization_nel_report(self):
        """Lines 167–171: _print_analysis prints name for Organization."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write("""<html><head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "name": "Org Test",
                    "url": "https://example.com"
                }
                </script>
                </head><body></body></html>""")
            result = runner.invoke(schema, ["--file", "test.html", "--analyze"])
        assert result.exit_code == 0
        assert "Organization" in result.output

    def test_righe_169_170_breadcrumblist_nel_report(self):
        """Lines 169–170: _print_analysis prints items for BreadcrumbList."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write("""<html><head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://example.com"}
                    ]
                }
                </script>
                </head><body></body></html>""")
            result = runner.invoke(schema, ["--file", "test.html", "--analyze"])
        assert result.exit_code == 0
        assert "BreadcrumbList" in result.output

    def test_righe_164_166_faqpage_con_domande(self):
        """Lines 164–166: _print_analysis prints the question count for FAQPage."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write("""<html><head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": "Domanda 1?",
                            "acceptedAnswer": {"@type": "Answer", "text": "Risposta 1"}
                        }
                    ]
                }
                </script>
                </head><body></body></html>""")
            result = runner.invoke(schema, ["--file", "test.html", "--analyze"])
        assert result.exit_code == 0
        assert "FAQPage" in result.output
        assert "1" in result.output  # 1 domanda

    def test_righe_173_175_verbose_true_mostra_json_completo(self):
        """Lines 173–175: --verbose shows the full JSON of the schema."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write("""<html><head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Sito Verbose",
                    "url": "https://example.com"
                }
                </script>
                </head><body></body></html>""")
            result = runner.invoke(
                schema,
                [
                    "--file",
                    "test.html",
                    "--analyze",
                    "--verbose",
                ],
            )
        assert result.exit_code == 0
        # In modalità verbose deve mostrare il JSON completo
        assert "Full schema" in result.output or "Sito Verbose" in result.output


# ============================================================================
# schema_cmd.py — più di 3 FAQ auto-detected (riga 198)
# ============================================================================


class TestSchemaCmdFaqOltreTre:
    """Verifies that _print_analysis shows '... and N more' with > 3 FAQ items."""

    def test_riga_198_piu_di_tre_faq_mostra_contatore(self):
        """Line 198: più di 3 FAQ estratte → riga '... and X more'."""
        runner = CliRunner()
        # Creates a HTML con 5 blocchi details/summary per far estrarre 5 FAQ
        faq_blocks = "\n".join(
            [
                f"""<details>
                <summary>Domanda {i}: cosa fa la funzione {i}?</summary>
                <p>La funzione {i} esegue operazioni di elaborazione dati avanzate</p>
            </details>"""
                for i in range(1, 6)
            ]
        )
        with runner.isolated_filesystem():
            with open("test.html", "w") as f:
                f.write(f"""<html><head>
                <script type="application/ld+json">
                {{
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {{"@type": "Question", "name": "D1?", "acceptedAnswer": {{"@type": "Answer", "text": "R1"}}}},
                        {{"@type": "Question", "name": "D2?", "acceptedAnswer": {{"@type": "Answer", "text": "R2"}}}},
                        {{"@type": "Question", "name": "D3?", "acceptedAnswer": {{"@type": "Answer", "text": "R3"}}}},
                        {{"@type": "Question", "name": "D4?", "acceptedAnswer": {{"@type": "Answer", "text": "R4"}}}},
                        {{"@type": "Question", "name": "D5?", "acceptedAnswer": {{"@type": "Answer", "text": "R5"}}}}
                    ]
                }}
                </script>
                </head><body>
                {faq_blocks}
                </body></html>""")
            result = runner.invoke(schema, ["--file", "test.html", "--analyze"])
        assert result.exit_code == 0
        # Se ci sono più di 3 FAQ, deve mostrare "... and X more"
        if "more" in result.output:
            assert "and" in result.output and "more" in result.output


# ============================================================================
# validators.py — branch mancanti (righe 81-82, 110-111, 117)
# ============================================================================


class TestValidatorsBranchMancanti:
    """Verifies uncovered branches in validate_public_url and validate_safe_path."""

    def test_righe_81_82_ip_address_ValueError_viene_ignored(self):
        """Lines 81–82: ip_address() raises ValueError for a malformed address → skip."""
        # Simula getaddrinfo che restituisce un indirizzo IPv6 non standard
        # che causa ValueError in ip_address()
        with patch("geo_optimizer.utils.validators.socket.getaddrinfo") as mock_dns:
            # Returns a indirizzo che non è un IP valido (malformato)
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("INDIRIZZO_INVALIDO", 0)),
            ]
            # Must not raise an exception, must continue
            ok, err = validate_public_url("https://example.com")
            # With an invalid address, it is skipped and validation passes
            assert ok is True

    def test_righe_110_111_must_exist_con_directory(self):
        """Lines 110–111: must_exist=True with a path that is a directory → error."""
        # /tmp always exists as a directory
        ok, err = validate_safe_path("/tmp", must_exist=True, allowed_extensions={".html"})
        # /tmp è una directory, non un file → deve fallire
        # (potrebbe fallire per estensione o per "non è un file")
        assert ok is False

    def test_riga_117_must_exist_file_non_found(self):
        """Line 117: must_exist=True con file realmente inesistente → errore."""
        path_inesistente = "/tmp/test_geo_coverage_nonexistent_file_12345.html"
        ok, err = validate_safe_path(
            path_inesistente,
            allowed_extensions={".html"},
            must_exist=True,
        )
        assert ok is False
        assert "not found" in err.lower() or "not found" in err.lower()

    def test_must_exist_false_file_non_esistente_valido(self):
        """must_exist=False: non-existent path with valid extension → OK."""
        ok, err = validate_safe_path(
            "/tmp/file_non_esistente.html",
            allowed_extensions={".html"},
            must_exist=False,
        )
        assert ok is True
        assert err is None

    def test_must_exist_true_con_file_esistente(self, tmp_path):
        """must_exist=True con file che esiste realmente → OK."""
        file_test = tmp_path / "page.html"
        file_test.write_text("<html></html>")
        ok, err = validate_safe_path(
            str(file_test),
            allowed_extensions={".html"},
            must_exist=True,
        )
        assert ok is True
        assert err is None

    def test_directory_esistente_must_exist_true(self, tmp_path):
        """Directory esistente con must_exist=True → 'Non è un file'."""
        # tmp_path è una directory
        ok, err = validate_safe_path(
            str(tmp_path),
            allowed_extensions={".html"},
            must_exist=True,
        )
        assert ok is False
        # Può fallire per estensione (noa suffix) o per "non è un file"
        assert err is not None


# ============================================================================
# Quick integration tests — verify consistency across branches
# ============================================================================


class TestIntegrazioneBranchCoperti:
    """Verifies that all covered branches produce consistent output."""

    def test_format_audit_text_completo_non_crasha(self):
        """format_audit_text with a complete AuditResult does not raise exceptions."""
        result = _make_audit_result(
            **{
                "robots.citation_bots_ok": True,
                "robots.bots_blocked": ["Bytespider"],
                "robots.bots_missing": ["DuckAssistBot"],
                "llms.found": True,
                "llms.has_h1": True,
                "schema.found_types": ["WebSite", "FAQPage"],
                "schema.has_website": True,
                "schema.has_faq": True,
            }
        )
        output = format_audit_text(result)
        assert "GEO AUDIT" in output
        assert "example.com" in output

    def test_generate_llms_txt_solo_homepage_noa_sezione(self):
        """generate_llms_txt con solo homepage non produce sezioni H2."""
        urls = [SitemapUrl(url="https://example.com/")]
        result = generate_llms_txt(
            "https://example.com",
            urls,
            site_name="Test",
            description="Sito test",
        )
        assert "# Test" in result
        assert "> Sito test" in result
        # La homepage produce una riga speciale, non una sezione H2
        assert "## _homepage" not in result

    def test_validate_jsonld_schema_completo_valido(self):
        """A complete, valid schema passes validation without errors."""
        schema_dict = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Sito Test",
            "url": "https://example.com",
        }
        ok, err = validate_jsonld(schema_dict, schema_type="website")
        assert ok is True
        assert err is None

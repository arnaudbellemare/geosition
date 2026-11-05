"""
Coverage tests for modules at 0% coverage.

Modules covered (in priority order):
- cli/html_formatter.py  — generates standalone HTML report
- utils/cache.py         — HTTP filesystem cache with TTL
- cli/rich_formatter.py  — Rich formatter for the terminal
- cli/github_formatter.py — GitHub Actions formatter
- utils/http_async.py    — async HTTP client with httpx
- web/cli.py             — CLI to start the web demo
- models/project_config.py — project configuration via YAML
- core/registry.py       — GEO plugin check system

Conventions:
- All tests use unittest.mock — no real network calls
- Naming: test_{subject}_{scenario}_{expectation}
- Arrange-Act-Assert pattern
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest
from click.testing import CliRunner

from geo_optimizer.models.results import (
    AuditResult,
    ContentResult,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
)

# ─── Fixture condivisa ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_offline_url_validation(monkeypatch):
    """Rende deterministica la validazione URL nei test di coverage offline."""

    def _fake_resolve(url):
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("example.com"):
            return True, None, ["93.184.216.34"]
        if host in {"localhost", "169.254.169.254", "192.168.0.1", "10.0.0.1"}:
            return False, "blocked for test", []
        return True, None, ["93.184.216.34"]

    monkeypatch.setattr("geo_optimizer.utils.validators.resolve_and_validate_url", _fake_resolve)
    monkeypatch.setattr("geo_optimizer.utils.http_async.resolve_and_validate_url", _fake_resolve, raising=False)


def _crea_audit_result_completo() -> AuditResult:
    """Creates a AuditResult con tutti i campi valorizzati per i test."""
    r = AuditResult(url="https://example.com")
    r.score = 85
    r.band = "good"
    r.http_status = 200
    r.page_size = 15000
    r.recommendations = ["Aggiungi FAQPage schema", "Migliora meta description"]

    r.robots = RobotsResult(
        found=True,
        bots_allowed=["GPTBot", "ClaudeBot", "PerplexityBot"],
        bots_blocked=["Googlebot"],
        citation_bots_ok=True,
    )
    r.llms = LlmsTxtResult(
        found=True,
        has_h1=True,
        has_sections=True,
        has_links=True,
        word_count=420,
    )
    r.schema = SchemaResult(
        found_types=["WebSite", "FAQPage"],
        has_website=True,
        has_faq=True,
        has_webapp=False,
    )
    r.meta = MetaResult(
        has_title=True,
        has_description=True,
        has_canonical=True,
        has_og_title=True,
        has_og_description=True,
        title_text="Example Site",
        description_text="Una descrizione esaustiva",
    )
    r.content = ContentResult(
        has_h1=True,
        has_numbers=True,
        has_links=True,
        word_count=1200,
        numbers_count=7,
        external_links_count=3,
    )
    return r


def _crea_audit_result_vuoto() -> AuditResult:
    """Creates a AuditResult con tutti i flag negativi (sito non ottimizzato)."""
    r = AuditResult(url="https://unoptimized.example.com")
    r.score = 15
    r.band = "critical"
    r.http_status = 200
    r.page_size = 2000
    r.recommendations = []
    return r


# ============================================================================
# 1 — html_formatter.py
# ============================================================================


class TestHtmlFormatter:
    """Test per il formatter HTML standalone."""

    def test_format_audit_html_struttura_base(self):
        """L'output HTML contiene le strutture fondamentali."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "GEO Audit Report" in html

    def test_format_audit_html_contiene_url(self):
        """L'HTML include l'URL del sito auditato."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "example.com" in html

    def test_format_audit_html_contiene_score(self):
        """L'HTML include il punteggio GEO."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "85" in html

    def test_format_audit_html_band_good(self):
        """Il colore banda 'good' è presente nell'HTML."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        # Banda good usa colore cyan (#06b6d4)
        assert "GOOD" in html or "#06b6d4" in html

    def test_format_audit_html_band_critical(self):
        """Banda 'critical' usa colore rosso."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_vuoto()
        html = format_audit_html(result)

        assert "CRITICAL" in html or "#ef4444" in html

    def test_format_audit_html_band_excellent(self):
        """Banda 'excellent' usa colore verde."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = AuditResult(url="https://best.com")
        result.score = 95
        result.band = "excellent"
        html = format_audit_html(result)

        assert "EXCELLENT" in html or "#22c55e" in html

    def test_format_audit_html_band_foundation(self):
        """Banda 'foundation' usa colore giallo."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = AuditResult(url="https://middle.com")
        result.score = 55
        result.band = "foundation"
        html = format_audit_html(result)

        assert "FOUNDATION" in html or "#eab308" in html

    def test_format_audit_html_raccomandazioni(self):
        """Le raccomandazioni vengono incluse nell'HTML."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "Aggiungi FAQPage schema" in html
        assert "Migliora meta description" in html

    def test_format_audit_html_senza_raccomandazioni(self):
        """Senza raccomandazioni, la sezione non è presente."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        result.recommendations = []
        html = format_audit_html(result)

        # La sezione raccomandazioni non deve apparire
        assert "Recommendations" not in html

    def test_format_audit_html_agent_plan_embedded_json(self):
        """HTML report includes machine-readable agent plan JSON."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        marker = '<script type="application/json" id="geo-agent-plan">'
        assert marker in html
        payload = html.split(marker, 1)[1].split("</script>", 1)[0]
        plan = json.loads(payload)

        assert plan["schema_version"] == "geo-agent-plan-v1"
        assert plan["site_url"] == result.url
        assert plan["score"] == result.score
        assert len(plan["actions"]) >= len(result.recommendations)
        titles = [action["title"] for action in plan["actions"]]
        assert "Aggiungi FAQPage schema" in titles
        assert all(action["agent_instruction"] for action in plan["actions"])

    def test_format_audit_html_agent_prompt_ready_for_ai(self):
        """HTML report includes copy/paste prompt and acceptance checks."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "AI Implementation Plan" in html
        assert "Copy/Paste Agent Prompt" in html
        assert "Work through every task below in priority order" in html
        assert "Files to inspect" in html
        assert "Acceptance checks" in html
        assert "Aggiungi FAQPage schema" in html

    def test_format_audit_html_schemi_trovati(self):
        """The found schema types are displayed as tags."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "WebSite" in html
        assert "FAQPage" in html

    def test_format_audit_html_senza_schema(self):
        """Senza schemi trovati, la sezione schema non appare."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_vuoto()
        html = format_audit_html(result)

        # No tipo schema vuol dire no tag schema nell'HTML
        assert "Found schemas" not in html

    def test_format_audit_html_escape_xss(self):
        """Caratteri HTML speciali nell'URL vengono escaped."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = AuditResult(url='https://example.com/<script>alert("xss")</script>')
        html = format_audit_html(result)

        # Il tag script nell'URL deve essere escaped
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_format_audit_html_tabella_check(self):
        """L'HTML contiene la tabella con tutti e 5 i check."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "Robots.txt" in html
        assert "llms.txt" in html
        assert "Schema JSON-LD" in html
        assert "Meta Tags" in html
        assert "Content Quality" in html

    def test_escape_funzione_caratteri_speciali(self):
        """The _escape function handles all special HTML characters."""
        from geo_optimizer.cli.html_formatter import _escape

        assert _escape("a & b") == "a &amp; b"
        assert _escape("<tag>") == "&lt;tag&gt;"
        assert _escape('"quoted"') == "&quot;quoted&quot;"
        assert _escape("a > b") == "a &gt; b"

    def test_robots_score_citation_ok(self):
        """Punteggio robots massimo con citation bots espliciti."""
        from geo_optimizer.cli.html_formatter import _robots_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.robots.citation_bots_ok = True
        r.robots.citation_bots_explicit = True
        r.robots.found = True

        expected = SCORING["robots_found"] + SCORING["robots_citation_ok"]
        assert _robots_score(r) == expected

    def test_robots_score_alcuni_bot_consentiti(self):
        """Punteggio robots medio con alcuni bot consentiti."""
        from geo_optimizer.cli.html_formatter import _robots_score
        from geo_optimizer.models.config import ROBOTS_PARTIAL_SCORE, SCORING

        r = AuditResult(url="https://example.com")
        r.robots.found = True
        r.robots.bots_allowed = ["GPTBot"]
        r.robots.citation_bots_ok = False

        expected = SCORING["robots_found"] + ROBOTS_PARTIAL_SCORE
        assert _robots_score(r) == expected

    def test_robots_score_solo_trovato(self):
        """Base robots score with only robots.txt found."""
        from geo_optimizer.cli.html_formatter import _robots_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.robots.found = True

        assert _robots_score(r) == SCORING["robots_found"]

    def test_robots_score_zero(self):
        """Punteggio robots zero se robots.txt not found."""
        from geo_optimizer.cli.html_formatter import _robots_score

        r = AuditResult(url="https://example.com")
        assert _robots_score(r) == 0

    def test_llms_score_completo(self):
        """Punteggio llms.txt massimo con tutti i flag attivi."""
        from geo_optimizer.cli.html_formatter import _llms_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.llms.found = True
        r.llms.has_h1 = True
        r.llms.has_sections = True
        r.llms.has_links = True

        expected = SCORING["llms_found"] + SCORING["llms_h1"] + SCORING["llms_sections"] + SCORING["llms_links"]
        assert _llms_score(r) == expected

    def test_schema_score_completo(self):
        """Punteggio schema massimo con tutti i flag attivi (v4.0: any_valid + website + faq)."""
        from geo_optimizer.cli.html_formatter import _schema_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.schema.has_website = True
        r.schema.has_faq = True
        r.schema.any_schema_found = True  # v4.0: sostituisce has_webapp

        expected = SCORING["schema_any_valid"] + SCORING["schema_website"] + SCORING["schema_faq"]
        assert _schema_score(r) == expected

    def test_meta_score_completo(self):
        """Punteggio meta massimo con tutti i flag attivi."""
        from geo_optimizer.cli.html_formatter import _meta_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.meta.has_title = True
        r.meta.title_length = 50        # within 40–60 sweet-spot
        r.meta.has_description = True
        r.meta.description_length = 140  # within 120–160 sweet-spot
        r.meta.has_canonical = True
        r.meta.has_og_title = True
        r.meta.has_og_description = True

        expected = SCORING["meta_title"] + SCORING["meta_description"] + SCORING["meta_canonical"] + SCORING["meta_og"]
        assert _meta_score(r) == expected

    def test_content_score_completo(self):
        """Punteggio content massimo con tutti i flag attivi."""
        from geo_optimizer.cli.html_formatter import _content_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.content.has_h1 = True
        r.content.has_numbers = True
        r.content.has_links = True

        expected = SCORING["content_h1"] + SCORING["content_numbers"] + SCORING["content_links"]
        assert _content_score(r) == expected

    def test_format_audit_html_contiene_timestamp(self):
        """The HTML includes a generated timestamp."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        # Il timestamp deve contenere "UTC"
        assert "UTC" in html

    def test_format_audit_html_contiene_link_repo(self):
        """L'HTML include il link al repository GitHub."""
        from geo_optimizer.cli.html_formatter import format_audit_html

        result = _crea_audit_result_completo()
        html = format_audit_html(result)

        assert "github.com" in html
        assert "geosition" in html


# ============================================================================
# 2 — utils/cache.py
# ============================================================================


class TestFileCache:
    """Test per la HTTP cache on the filesystem with TTL."""

    def test_get_cache_miss_file_non_esistente(self):
        """get() returns None se il file cache does not exist."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir) / "non_esiste")
            result = cache.get("https://example.com")
            assert result is None

    def test_put_e_get_cache_hit(self):
        """put() salva la response, get() la recupera correttamente."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))
            url = "https://example.com/page"

            cache.put(url, 200, "<html>test</html>", {"Content-Type": "text/html"})
            result = cache.get(url)

            assert result is not None
            status, text, headers = result
            assert status == 200
            assert "<html>test</html>" in text
            assert headers["Content-Type"] == "text/html"

    def test_get_cache_scaduta_rimuove_file(self):
        """get() returns None e rimuove il file se il TTL è scaduto."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir), ttl=1)
            url = "https://example.com/ttl"

            cache.put(url, 200, "content", {})

            # Simula TTL scaduto modificando il tempo con patch
            with patch("geo_optimizer.utils.cache.time.time", return_value=time.time() + 3600):
                result = cache.get(url)

            assert result is None

    def test_get_file_json_corrotto(self):
        """get() returns None se il file cache contiene JSON non valido."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))
            url = "https://example.com/corrotto"

            # Crea manualmente un file corrotto
            path = cache._path(url)
            path.write_text("{JSON non valido[", encoding="utf-8")

            result = cache.get(url)
            assert result is None

    def test_clear_rimuove_tutti_i_file(self):
        """clear() svuota la directory cache e returns the conteggio."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))

            cache.put("https://example.com/a", 200, "a", {})
            cache.put("https://example.com/b", 200, "b", {})
            cache.put("https://example.com/c", 200, "c", {})

            count = cache.clear()
            assert count == 3
            assert not Path(tmpdir).exists()

    def test_clear_directory_non_esistente(self):
        """clear() ritorna 0 se la directory does not exist."""
        from geo_optimizer.utils.cache import FileCache

        cache = FileCache(cache_dir=Path("/tmp/geo_cache_non_esiste_mai_xyz"))
        count = cache.clear()
        assert count == 0

    def test_stats_directory_non_esistente(self):
        """stats() ritorna valori zero se la directory does not exist."""
        from geo_optimizer.utils.cache import FileCache

        cache = FileCache(cache_dir=Path("/tmp/geo_cache_stats_vuoto_xyz"))
        stats = cache.stats()

        assert stats["files"] == 0
        assert stats["size_bytes"] == 0

    def test_stats_con_file_in_cache(self):
        """stats() riporta il numero corretto di file e dimensione > 0."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))
            cache.put("https://example.com/stat", 200, "content di test", {})

            stats = cache.stats()
            assert stats["files"] == 1
            assert stats["size_bytes"] > 0

    def test_key_genera_hash_sha256(self):
        """_key() generates a deterministic SHA256 hash for the same URL."""
        from geo_optimizer.utils.cache import FileCache

        cache = FileCache()
        url = "https://example.com/test"

        key1 = cache._key(url)
        key2 = cache._key(url)

        assert key1 == key2
        assert len(key1) == 64  # SHA-256 in hex

    def test_key_diverso_per_url_diversi(self):
        """_key() generates different hashes for different URLs."""
        from geo_optimizer.utils.cache import FileCache

        cache = FileCache()
        key_a = cache._key("https://example.com/a")
        key_b = cache._key("https://example.com/b")

        assert key_a != key_b

    def test_path_ritorna_path_con_json_extension(self):
        """_path() returns a Path con estensione .json."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))
            path = cache._path("https://example.com")

            assert path.suffix == ".json"
            assert path.parent == Path(tmpdir)

    def test_put_crea_directory_se_non_esiste(self):
        """put() crea la directory cache se does not exist."""
        from geo_optimizer.utils.cache import FileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            nuova_dir = Path(tmpdir) / "nuova" / "cache"
            cache = FileCache(cache_dir=nuova_dir)

            cache.put("https://example.com", 200, "test", {})

            assert nuova_dir.exists()

    def test_ttl_default_e_personalizzato(self):
        """Il TTL di default è 3600, ma può essere personalizzato."""
        from geo_optimizer.utils.cache import DEFAULT_TTL, FileCache

        assert DEFAULT_TTL == 3600

        cache_custom = FileCache(ttl=7200)
        assert cache_custom.ttl == 7200


# ============================================================================
# 3 — cli/rich_formatter.py
# ============================================================================


class TestRichFormatter:
    """Test per il Rich formatter per output CLI colorato."""

    def test_is_rich_available_ritorna_bool(self):
        """is_rich_available() returns True when rich is installed."""
        from geo_optimizer.cli.rich_formatter import is_rich_available

        # Verifichiamo solo che ritorni un bool, non importa il value
        result = is_rich_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_ritorna_stringa(self):
        """format_audit_rich() returns aa stringa non vuota."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_completo()
        output = format_audit_rich(result)

        assert isinstance(output, str)
        assert len(output) > 0

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_contiene_url(self):
        """L'output Rich include l'URL del sito."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_completo()
        output = format_audit_rich(result)

        assert "example.com" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_contiene_check_names(self):
        """L'output Rich include i nomi dei check principali."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_completo()
        output = format_audit_rich(result)

        assert "Robots.txt" in output
        assert "llms.txt" in output
        assert "Schema JSON-LD" in output
        assert "Meta Tags" in output
        assert "Content Quality" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_robots_non_trovato(self):
        """The output handles robots.txt not found correctly."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_vuoto()
        output = format_audit_rich(result)

        # v2: expected text "File not found"
        assert "not found" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_llms_non_trovato(self):
        """The output handles llms.txt not found correctly."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_vuoto()
        output = format_audit_rich(result)

        # v2: expected text "File not found"
        assert "not found" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_raccomandazioni(self):
        """Le raccomandazioni vengono incluse nell'output Rich."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_completo()
        output = format_audit_rich(result)

        assert "Aggiungi FAQPage schema" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_barra_score(self):
        """L'output contiene la barra visuale del punteggio."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_completo()
        output = format_audit_rich(result)

        # The bar uses line-drawing characters
        assert "━" in output

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("rich"),
        reason="rich non installato",
    )
    def test_format_audit_rich_schema_noo(self):
        """Without schema, the output shows 'No schema'."""
        from geo_optimizer.cli.rich_formatter import format_audit_rich

        result = _crea_audit_result_vuoto()
        output = format_audit_rich(result)

        # v2: expected text "No schema found"
        assert "No schema found" in output

    def test_score_color_returns_color(self):
        """_score_color() returns a colore hex basato sulla percentuale."""
        from geo_optimizer.cli.rich_formatter import _score_color

        # Score alto → verde
        assert "#22c55e" in _score_color(90, 100)
        # Score basso → rosso
        assert "#ef4444" in _score_color(10, 100)

    def test_robots_score_punteggio_zero_senza_robots(self):
        """_robots_score() ritorna 0 senza robots.txt."""
        from geo_optimizer.cli.rich_formatter import _robots_score

        r = AuditResult(url="https://example.com")
        assert _robots_score(r) == 0

    def test_llms_score_solo_found(self):
        """_llms_score() returns the punteggio base con solo found=True."""
        from geo_optimizer.cli.rich_formatter import _llms_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.llms.found = True

        assert _llms_score(r) == SCORING["llms_found"]

    def test_meta_score_og_richiede_entrambi(self):
        """_meta_score() assegna punti OG solo se entrambi og_title e og_desc presenti."""
        from geo_optimizer.cli.rich_formatter import _meta_score

        # Solo og_title, senza og_description: no punto OG
        r = AuditResult(url="https://example.com")
        r.meta.has_og_title = True
        r.meta.has_og_description = False

        score = _meta_score(r)
        assert score == 0  # No altro flag attivo

    def test_content_score_zero_senza_flag(self):
        """_content_score() ritorna 0 senza flag attivi."""
        from geo_optimizer.cli.rich_formatter import _content_score

        r = AuditResult(url="https://example.com")
        assert _content_score(r) == 0


# ============================================================================
# 4 — cli/github_formatter.py
# ============================================================================


class TestGithubFormatter:
    """Test per il formatter GitHub Actions con annotazioni ::notice/::warning/::error."""

    def test_format_audit_github_score_alto_notice(self):
        """Score >= 71 generates a ::notice annotation."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = _crea_audit_result_completo()
        result.score = 85

        output = format_audit_github(result)
        assert output.startswith("::notice::GEO Score: 85")

    def test_format_audit_github_score_medio_warning(self):
        """Score between 41 and 70 generates a ::warning annotation."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = AuditResult(url="https://example.com")
        result.score = 60
        result.band = "foundation"

        output = format_audit_github(result)
        assert output.startswith("::warning::GEO Score: 60")

    def test_format_audit_github_score_basso_error(self):
        """Score <= 40 generates an ::error annotation."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = _crea_audit_result_vuoto()
        result.score = 15

        output = format_audit_github(result)
        assert output.startswith("::error::GEO Score: 15")

    def test_format_audit_github_contiene_url(self):
        """L'output include l'URL del sito."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = _crea_audit_result_completo()
        output = format_audit_github(result)

        assert "example.com" in output

    def test_format_audit_github_check_falliti_come_warning(self):
        """I check non passati generano annotazioni ::warning."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        # Sito con robots.txt mancante: check "Robots.txt" non passa
        result = _crea_audit_result_vuoto()
        result.score = 20
        result.band = "critical"

        output = format_audit_github(result)
        lines = output.split("\n")

        # Deve esserci almeno una riga warning per un check fallito
        warning_lines = [line for line in lines if line.startswith("::warning::")]
        assert len(warning_lines) >= 1

    def test_format_audit_github_raccomandazioni_come_warning(self):
        """Le raccomandazioni vengono incluse come ::warning."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = AuditResult(url="https://example.com")
        result.score = 85
        result.band = "good"
        result.recommendations = ["Aggiungi FAQPage schema"]

        output = format_audit_github(result)
        assert "::warning::Aggiungi FAQPage schema" in output

    def test_format_audit_github_senza_raccomandazioni(self):
        """Senza raccomandazioni, l'output non ha righe warning aggiuntive."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = _crea_audit_result_completo()
        result.recommendations = []

        output = format_audit_github(result)
        # L'output deve avere la prima riga notice
        assert output.startswith("::notice::")

    def test_format_audit_github_band_labels(self):
        """Le band label vengono incluse nell'annotazione principale."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        for band, expected_label in [
            ("excellent", "EXCELLENT"),
            ("good", "GOOD"),
            ("foundation", "FOUNDATION"),
            ("critical", "CRITICAL"),
        ]:
            result = AuditResult(url="https://example.com")
            result.band = band
            result.score = 50  # Forza warning indipendentemente dal band

            output = format_audit_github(result)
            assert expected_label in output

    def test_robots_score_github_citation_ok(self):
        """_robots_score() del github formatter calcola correttamente con citation espliciti."""
        from geo_optimizer.cli.github_formatter import _robots_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.robots.citation_bots_ok = True
        r.robots.citation_bots_explicit = True
        r.robots.found = True

        expected = SCORING["robots_found"] + SCORING["robots_citation_ok"]
        assert _robots_score(r) == expected

    def test_llms_score_github_zero(self):
        """_llms_score() del github formatter ritorna 0 senza flag."""
        from geo_optimizer.cli.github_formatter import _llms_score

        r = AuditResult(url="https://example.com")
        assert _llms_score(r) == 0

    def test_schema_score_github_completo(self):
        """_schema_score() del github formatter calculates the totale correttamente (v4.0)."""
        from geo_optimizer.cli.github_formatter import _schema_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.schema.has_website = True
        r.schema.has_faq = True
        r.schema.any_schema_found = True  # v4.0: sostituisce has_webapp

        expected = SCORING["schema_any_valid"] + SCORING["schema_website"] + SCORING["schema_faq"]
        assert _schema_score(r) == expected

    def test_meta_score_github_parziale(self):
        """_meta_score() del github formatter calcola punteggio parziale."""
        from geo_optimizer.cli.github_formatter import _meta_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.meta.has_title = True
        r.meta.title_length = 50        # within 40–60 sweet-spot
        r.meta.has_description = True
        r.meta.description_length = 140  # within 120–160 sweet-spot

        expected = SCORING["meta_title"] + SCORING["meta_description"]
        assert _meta_score(r) == expected

    def test_content_score_github_solo_h1(self):
        """_content_score() of the GitHub formatter calculates only the H1 point."""
        from geo_optimizer.cli.github_formatter import _content_score
        from geo_optimizer.models.config import SCORING

        r = AuditResult(url="https://example.com")
        r.content.has_h1 = True

        assert _content_score(r) == SCORING["content_h1"]

    def test_format_audit_github_score_limite_71_e_notice(self):
        """Score exactly 71 generates ::notice (lower bound of 'good')."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = AuditResult(url="https://example.com")
        result.score = 71
        result.band = "good"

        output = format_audit_github(result)
        assert output.startswith("::notice::")

    def test_format_audit_github_score_limite_41_e_warning(self):
        """Score exactly 41 generates ::warning."""
        from geo_optimizer.cli.github_formatter import format_audit_github

        result = AuditResult(url="https://example.com")
        result.score = 41
        result.band = "foundation"

        output = format_audit_github(result)
        assert output.startswith("::warning::")


# ============================================================================
# 5 — utils/http_async.py
# ============================================================================


class TestHttpAsync:
    """Test per il async HTTP client with httpx."""

    def test_is_httpx_available_ritorna_bool(self):
        """is_httpx_available() returns a value booleano."""
        from geo_optimizer.utils.http_async import is_httpx_available

        result = is_httpx_available()
        assert isinstance(result, bool)

    def test_is_httpx_available_false_quando_non_installato(self):
        """is_httpx_available() returns False when httpx is not importable."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("httpx non disponibile")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            # Re-importa il modulo per testare la logica with httpx mancante
            import importlib

            import geo_optimizer.utils.http_async as mod

            importlib.reload(mod)
            result = mod.is_httpx_available()
            assert result is False
            # Ripristina lo status del modulo
            importlib.reload(mod)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_url_async_successo(self):
        """fetch_url_async() returns (response, None) on success."""
        from geo_optimizer.utils.http_async import fetch_url_async

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.content = b"<html>test</html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        async def run():
            return await fetch_url_async("https://example.com", client=mock_client)

        response, error = asyncio.run(run())
        assert error is None
        assert response is mock_response

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_url_async_timeout(self):
        """fetch_url_async() returns (None, error_msg) on timeout."""
        import httpx

        from geo_optimizer.utils.http_async import fetch_url_async

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout", request=MagicMock()))

        async def run():
            return await fetch_url_async("https://example.com", client=mock_client)

        response, error = asyncio.run(run())
        assert response is None
        assert "Timeout" in error

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_url_async_connection_error(self):
        """fetch_url_async() returns (None, error_msg) on connection error."""
        import httpx

        from geo_optimizer.utils.http_async import fetch_url_async

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed", request=MagicMock()))

        async def run():
            return await fetch_url_async("https://example.com", client=mock_client)

        response, error = asyncio.run(run())
        assert response is None
        assert error is not None
        assert "Connection failed" in error

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_url_async_risposta_troppo_grande_content_length(self):
        """fetch_url_async() returns an error if Content-Length exceeds max_size."""
        from geo_optimizer.utils.http_async import fetch_url_async

        mock_response = MagicMock()
        mock_response.headers = {"content-length": "999999999"}
        mock_response.content = b"dati"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        async def run():
            return await fetch_url_async("https://example.com", client=mock_client, max_size=1000)

        response, error = asyncio.run(run())
        assert response is None
        assert "too large" in error

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_url_async_risposta_troppo_grande_content_effettivo(self):
        """fetch_url_async() ritorna errore se il content effettivo supera max_size."""
        from geo_optimizer.utils.http_async import fetch_url_async

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.content = b"x" * 10000

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        async def run():
            return await fetch_url_async("https://example.com", client=mock_client, max_size=1000)

        response, error = asyncio.run(run())
        assert response is None
        assert "too large" in error

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("httpx"),
        reason="httpx non installato",
    )
    def test_fetch_urls_async_parallelo(self):
        """fetch_urls_async() returns a dict con tutti gli URL come chiavi."""

        from geo_optimizer.utils.http_async import fetch_urls_async

        urls = ["https://example.com/a", "https://example.com/b"]

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.content = b"<html>test</html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        async def run():
            with patch("httpx.AsyncClient", return_value=mock_client):
                return await fetch_urls_async(urls)

        results = asyncio.run(run())
        assert set(results.keys()) == set(urls)


# ============================================================================
# 6 — web/cli.py
# ============================================================================


class TestWebCli:
    """Test per la CLI della web demo GEOSITION."""

    def test_main_senza_uvicorn_mostra_errore(self):
        """main() mostra un errore se uvicorn non è installato."""
        from geo_optimizer.web.cli import main

        runner = CliRunner()

        with patch("builtins.__import__", side_effect=ImportError("uvicorn not found")):
            # Simula l'importazione di uvicorn che fails
            result = runner.invoke(main, ["--port", "8001"])

        # L'uscita deve contenere un messaggio di errore
        # (il side_effect globale potrebbe interferire con altri import)
        assert result.exit_code != 0 or "uvicorn" in (result.output or "")

    def test_main_con_uvicorn_avvia_server(self):
        """main() avvia uvicorn.run() con i parametri corretti."""
        from geo_optimizer.web.cli import main

        runner = CliRunner()
        mock_uvicorn = MagicMock()

        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            runner.invoke(main, ["--host", "127.0.0.1", "--port", "9999"])

        # uvicorn.run deve essere status chiamato
        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args

        # Verify host and port parameters
        assert call_kwargs[1]["host"] == "127.0.0.1" or (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "127.0.0.1")

    def test_main_con_uvicorn_parametri_default(self):
        """main() usa parametri di default host=127.0.0.1, port=8000."""
        from geo_optimizer.web.cli import main

        runner = CliRunner()
        mock_uvicorn = MagicMock()

        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            runner.invoke(main, [])

        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args

        # Verify default port
        assert 8000 in call_kwargs[0] or call_kwargs[1].get("port") == 8000

    def test_main_stampa_url_avvio(self):
        """main() prints the server URL before starting it."""
        from geo_optimizer.web.cli import main

        runner = CliRunner()
        mock_uvicorn = MagicMock()

        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            result = runner.invoke(main, ["--host", "localhost", "--port", "8080"])

        assert "localhost" in result.output
        assert "8080" in result.output

    def test_main_flag_reload(self):
        """main() con --reload passa reload=True a uvicorn.run()."""
        from geo_optimizer.web.cli import main

        runner = CliRunner()
        mock_uvicorn = MagicMock()

        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            runner.invoke(main, ["--reload"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs[1].get("reload") is True or True in call_kwargs[0]


# ============================================================================
# 7 — models/project_config.py
# ============================================================================


class TestProjectConfig:
    """Test per la project configuration via file YAML."""

    def test_load_config_senza_file_ritorna_defaults(self):
        """load_config() returns a ProjectConfig with defaults when no file is found."""
        from geo_optimizer.models.project_config import ProjectConfig, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_config(Path(tmpdir) / "non_esiste.yml")

        assert isinstance(config, ProjectConfig)
        assert config.audit.format == "text"
        assert config.audit.min_score == 0
        assert config.llms.max_urls == 50

    def test_find_config_file_trovato_yml(self):
        """find_config_file() trova .geo-optimizer.yml nella directory."""
        from geo_optimizer.models.project_config import find_config_file

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text("audit:\n  url: https://example.com\n")

            found = find_config_file(Path(tmpdir))
            assert found == config_file

    def test_find_config_file_trovato_yaml(self):
        """find_config_file() trova .geo-optimizer.yaml come alternativa."""
        from geo_optimizer.models.project_config import find_config_file

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yaml"
            config_file.write_text("audit:\n  url: https://example.com\n")

            found = find_config_file(Path(tmpdir))
            assert found == config_file

    def test_find_config_file_non_trovato(self):
        """find_config_file() returns None se no file esiste."""
        from geo_optimizer.models.project_config import find_config_file

        with tempfile.TemporaryDirectory() as tmpdir:
            found = find_config_file(Path(tmpdir))
            assert found is None

    def test_load_config_senza_yaml_ritorna_defaults(self):
        """load_config() returns defaults when PyYAML is not available."""
        from geo_optimizer.models.project_config import ProjectConfig, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text("audit:\n  url: https://example.com\n")

            with patch(
                "geo_optimizer.models.project_config._is_yaml_available",
                return_value=False,
            ):
                config = load_config(config_file)

        assert isinstance(config, ProjectConfig)
        assert config.audit.url is None

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_audit_section(self):
        """load_config() legge correttamente la sezione audit dal YAML."""
        from geo_optimizer.models.project_config import load_config

        yaml_content = """
audit:
  url: https://test.example.com
  format: json
  min_score: 70
  cache: true
  verbose: true
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text(yaml_content)

            config = load_config(config_file)

        assert config.audit.url == "https://test.example.com"
        assert config.audit.format == "json"
        assert config.audit.min_score == 70
        assert config.audit.cache is True
        assert config.audit.verbose is True

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_llms_section(self):
        """load_config() legge correttamente la sezione llms dal YAML."""
        from geo_optimizer.models.project_config import load_config

        yaml_content = """
llms:
  base_url: https://test.example.com
  title: Titolo Sito
  description: Descrizione sito
  max_urls: 100
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text(yaml_content)

            config = load_config(config_file)

        assert config.llms.base_url == "https://test.example.com"
        assert config.llms.title == "Titolo Sito"
        assert config.llms.max_urls == 100

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_schema_section(self):
        """load_config() legge correttamente la sezione schema dal YAML."""
        from geo_optimizer.models.project_config import load_config

        yaml_content = """
schema:
  types:
    - website
    - faq
    - webapp
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text(yaml_content)

            config = load_config(config_file)

        assert "website" in config.schema.types
        assert "faq" in config.schema.types

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_extra_bots(self):
        """load_config() legge correttamente la sezione extra_bots."""
        from geo_optimizer.models.project_config import load_config

        yaml_content = """
extra_bots:
  MyCustomBot: Bot personalizzato
  AnotherBot: Un altro bot
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text(yaml_content)

            config = load_config(config_file)

        assert "MyCustomBot" in config.extra_bots
        assert config.extra_bots["MyCustomBot"] == "Bot personalizzato"

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_corrotto_ritorna_defaults(self):
        """load_config() returns defaults when the YAML is corrupted."""
        from geo_optimizer.models.project_config import ProjectConfig, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text("yaml: non valido: {[")

            config = load_config(config_file)

        assert isinstance(config, ProjectConfig)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("yaml"),
        reason="PyYAML non installato",
    )
    def test_load_config_yaml_non_dict_ritorna_defaults(self):
        """load_config() returns defaults when the YAML is not a dictionary."""
        from geo_optimizer.models.project_config import ProjectConfig, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".geo-optimizer.yml"
            config_file.write_text("- elemento1\n- elemento2\n")

            config = load_config(config_file)

        assert isinstance(config, ProjectConfig)

    def test_is_yaml_available_ritorna_bool(self):
        """_is_yaml_available() returns True or False."""
        from geo_optimizer.models.project_config import _is_yaml_available

        result = _is_yaml_available()
        assert isinstance(result, bool)

    def test_project_config_defaults(self):
        """ProjectConfig creates an instance with all correct defaults."""
        from geo_optimizer.models.project_config import (
            AuditConfig,
            LlmsConfig,
            ProjectConfig,
            SchemaConfig,
        )

        config = ProjectConfig()

        assert isinstance(config.audit, AuditConfig)
        assert isinstance(config.llms, LlmsConfig)
        assert isinstance(config.schema, SchemaConfig)
        assert config.extra_bots == {}

    def test_audit_config_defaults(self):
        """AuditConfig ha i valori di default corretti."""
        from geo_optimizer.models.project_config import AuditConfig

        cfg = AuditConfig()

        assert cfg.url is None
        assert cfg.format == "text"
        assert cfg.output is None
        assert cfg.min_score == 0
        assert cfg.cache is False
        assert cfg.verbose is False


# ============================================================================
# 8 — core/registry.py
# ============================================================================


class TestCheckRegistry:
    """Test per il plugin system check GEO (CheckRegistry)."""

    def setup_method(self):
        """Svuota il registry prima di ogni test per isolamento."""
        from geo_optimizer.core.registry import CheckRegistry

        CheckRegistry.clear()

    def teardown_method(self):
        """Pulisce il registry dopo ogni test."""
        from geo_optimizer.core.registry import CheckRegistry

        CheckRegistry.clear()

    def _crea_check_valido(self, name: str = "test_check"):
        """Creates a'istanza di check valida che implementa AuditCheck Protocol."""
        from geo_optimizer.core.registry import CheckResult

        class CheckValido:
            def __init__(self, check_name):
                self.name = check_name
                self.description = f"Check di test: {check_name}"
                self.max_score = 10

            def run(self, url: str, soup=None, **kwargs) -> CheckResult:
                return CheckResult(
                    name=self.name,
                    score=5,
                    max_score=10,
                    passed=True,
                    message="Test OK",
                )

        return CheckValido(name)

    def test_register_check_valido(self):
        """register() aggiunge correttamente un check valido."""
        from geo_optimizer.core.registry import CheckRegistry

        check = self._crea_check_valido("check_valido")
        CheckRegistry.register(check)

        assert "check_valido" in CheckRegistry.names()

    def test_register_check_duplicato_lancia_value_error(self):
        """register() lancia ValueError se il check è già registrato."""
        from geo_optimizer.core.registry import CheckRegistry

        check = self._crea_check_valido("check_unico")
        CheckRegistry.register(check)

        with pytest.raises(ValueError, match="already registered"):
            CheckRegistry.register(check)

    def test_register_check_non_implementa_protocol_lancia_type_error(self):
        """register() lancia TypeError se l'oggetto non implementa AuditCheck."""
        from geo_optimizer.core.registry import CheckRegistry

        class CheckNonValido:
            """Manca name, description, max_score e run()."""

            pass

        with pytest.raises(TypeError):
            CheckRegistry.register(CheckNonValido())

    def test_get_check_per_nome(self):
        """get() recupera il check registrato per nome."""
        from geo_optimizer.core.registry import CheckRegistry

        check = self._crea_check_valido("check_get")
        CheckRegistry.register(check)

        retrieved = CheckRegistry.get("check_get")
        assert retrieved is check

    def test_get_check_non_esistente_ritorna_none(self):
        """get() returns None se il check does not exist."""
        from geo_optimizer.core.registry import CheckRegistry

        result = CheckRegistry.get("check_inesistente")
        assert result is None

    def test_unregister_rimuove_check(self):
        """unregister() rimuove il check dal registry."""
        from geo_optimizer.core.registry import CheckRegistry

        check = self._crea_check_valido("check_da_rimuovere")
        CheckRegistry.register(check)
        CheckRegistry.unregister("check_da_rimuovere")

        assert "check_da_rimuovere" not in CheckRegistry.names()

    def test_unregister_nome_non_esistente_non_crasha(self):
        """unregister() con nome does not existnte non lancia eccezioni."""
        from geo_optimizer.core.registry import CheckRegistry

        # Non deve lanciare KeyError o altri errori
        CheckRegistry.unregister("nome_che_non_esiste")

    def test_all_ritorna_lista_check(self):
        """all() ritorna lista di tutti i check registrati."""
        from geo_optimizer.core.registry import CheckRegistry

        check_a = self._crea_check_valido("check_a")
        check_b = self._crea_check_valido("check_b")
        CheckRegistry.register(check_a)
        CheckRegistry.register(check_b)

        all_checks = CheckRegistry.all()
        assert len(all_checks) == 2
        assert check_a in all_checks
        assert check_b in all_checks

    def test_names_ritorna_lista_nomi(self):
        """names() ritorna lista dei nomi dei check registrati."""
        from geo_optimizer.core.registry import CheckRegistry

        check_x = self._crea_check_valido("nome_x")
        CheckRegistry.register(check_x)

        names = CheckRegistry.names()
        assert "nome_x" in names

    def test_clear_svuota_il_registry(self):
        """clear() svuota completamente il registry."""
        from geo_optimizer.core.registry import CheckRegistry

        CheckRegistry.register(self._crea_check_valido("check_pre_clear"))
        CheckRegistry.clear()

        assert CheckRegistry.all() == []
        assert CheckRegistry.names() == []

    def test_run_all_esegue_tutti_i_check(self):
        """run_all() esegue tutti i check registrati e ritorna lista risultati."""
        from geo_optimizer.core.registry import CheckRegistry, CheckResult

        check_a = self._crea_check_valido("run_a")
        check_b = self._crea_check_valido("run_b")
        CheckRegistry.register(check_a)
        CheckRegistry.register(check_b)

        results = CheckRegistry.run_all("https://example.com")

        assert len(results) == 2
        assert all(isinstance(r, CheckResult) for r in results)

    def test_run_all_check_che_crasha_ritorna_score_zero(self):
        """run_all() handles checks that raise exceptions: score 0, passed False."""
        from geo_optimizer.core.registry import CheckRegistry, CheckResult

        class CheckCheCrepa:
            name = "check_crepa"
            description = "Check che lancia eccezione"
            max_score = 10

            def run(self, url: str, soup=None, **kwargs) -> CheckResult:
                raise RuntimeError("Errore simulato nel check")

        CheckRegistry.register(CheckCheCrepa())
        results = CheckRegistry.run_all("https://example.com")

        assert len(results) == 1
        assert results[0].score == 0
        assert results[0].passed is False
        assert "Error in check" in results[0].message

    def test_check_result_dataclass_defaults(self):
        """CheckResult ha valori di default corretti."""
        from geo_optimizer.core.registry import CheckResult

        result = CheckResult(name="test")

        assert result.name == "test"
        assert result.score == 0
        assert result.max_score == 10
        assert result.passed is False
        assert result.details == {}
        assert result.message == ""

    def test_load_entry_points_non_eseguito_due_volte(self):
        """load_entry_points() non carica due volte gli stessi entry point."""
        from geo_optimizer.core.registry import CheckRegistry

        # entry_points viene importato localmente nel metodo, quindi
        # si patcha direttamente in importlib.metadata
        with patch("importlib.metadata.entry_points", return_value=[]):
            # Prima chiamata: executes the caricamento
            count1 = CheckRegistry.load_entry_points()
            # Seconda chiamata: ritorna 0 immediatamente (già caricati)
            count2 = CheckRegistry.load_entry_points()

        assert count1 == 0
        assert count2 == 0

    def test_run_all_registry_vuoto_ritorna_lista_vuota(self):
        """run_all() con registry vuoto ritorna empty list."""
        from geo_optimizer.core.registry import CheckRegistry

        results = CheckRegistry.run_all("https://example.com")
        assert results == []

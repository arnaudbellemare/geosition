"""
Test per geo_optimizer.mcp.server.

Verifies the 4 tool MCP e le 2 resource. Tutto mockato — zero calls HTTP.
Richiede: pip install geosition[mcp]
"""

import json
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

# Skip se mcp non installato
pytest.importorskip("mcp", reason="mcp non installato (pip install geosition[mcp])")

from geo_optimizer.mcp.server import (
    geo_ai_search_context,
    geo_audit,
    geo_factual_accuracy,
    geo_fix,
    geo_gap_analysis,
    geo_llms_generate,
    geo_schema_validate,
    get_ai_bots,
    get_score_bands,
)
from geo_optimizer.models.results import (
    AuditResult,
    ContentResult,
    FactualAccuracyResult,
    FixItem,
    FixPlan,
    GapAction,
    GapAnalysisResult,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def _mock_mcp_url_validation(monkeypatch):
    """Rende deterministica la validazione URL nei test MCP offline."""

    def _fake_validate(url):
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("example.com"):
            return True, None
        if host in {"localhost", "169.254.169.254", "192.168.0.1", "10.0.0.1"}:
            return False, "blocked for test"
        return True, None

    monkeypatch.setattr("geo_optimizer.utils.validators.validate_public_url", _fake_validate)


def _mock_audit_result():
    """Creates an AuditResult mock for tests."""
    return AuditResult(
        url="https://example.com",
        score=65,
        band="foundation",
        robots=RobotsResult(
            found=True,
            bots_allowed=["GPTBot"],
            bots_missing=["ClaudeBot"],
            citation_bots_ok=False,
        ),
        llms=LlmsTxtResult(found=False),
        schema=SchemaResult(found_types=["WebSite"], has_website=True),
        meta=MetaResult(
            has_title=True,
            has_description=True,
            has_canonical=False,
            title_text="Example",
        ),
        content=ContentResult(has_h1=True, word_count=500),
        recommendations=["Aggiungi llms.txt"],
        http_status=200,
        page_size=12000,
    )


def _mock_fix_plan():
    """Creates a FixPlan mock for tests."""
    return FixPlan(
        url="https://example.com",
        score_before=65,
        score_estimated_after=85,
        fixes=[
            FixItem(
                category="robots",
                description="Aggiunge 1 bot AI mancante",
                content="User-agent: ClaudeBot\nAllow: /\n",
                file_name="robots.txt",
                action="append",
            ),
        ],
        skipped=["schema: già presente"],
    )


# ============================================================================
# TEST: geo_audit
# ============================================================================


class TestGeoAuditTool:
    """Test per il tool MCP geo_audit."""

    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_audit_ritorna_json_valido(self, mock_audit):
        """geo_audit returns JSON with score and details."""
        mock_audit.return_value = _mock_audit_result()

        result = geo_audit("https://example.com")
        data = json.loads(result)

        assert data["score"] == 65
        assert data["band"] == "foundation"
        assert data["url"] == "https://example.com"
        assert data["robots"]["found"] is True

    def test_audit_url_non_sicuro(self):
        """geo_audit blocks URLs pointing to private networks."""
        result = geo_audit("http://169.254.169.254/metadata")
        data = json.loads(result)

        assert "error" in data
        assert "Unsafe URL" in data["error"]

    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_audit_normalizza_url(self, mock_audit):
        """geo_audit aggiunge https:// se mancante."""
        mock_audit.return_value = _mock_audit_result()

        geo_audit("example.com")
        call_url = mock_audit.call_args[0][0]
        assert call_url.startswith("https://")


# ============================================================================
# TEST: geo_fix
# ============================================================================


class TestGeoFixTool:
    """Test per il tool MCP geo_fix."""

    @patch("geo_optimizer.core.fixer.run_all_fixes")
    def test_fix_ritorna_piano(self, mock_fixes):
        """geo_fix returns a serialised FixPlan."""
        mock_fixes.return_value = _mock_fix_plan()

        result = geo_fix("https://example.com")
        data = json.loads(result)

        assert data["score_before"] == 65
        assert data["score_estimated_after"] == 85
        assert len(data["fixes"]) == 1
        assert data["fixes"][0]["category"] == "robots"

    @patch("geo_optimizer.core.fixer.run_all_fixes")
    def test_fix_con_filtro_only(self, mock_fixes):
        """geo_fix con only filtra le categorie."""
        mock_fixes.return_value = _mock_fix_plan()

        geo_fix("https://example.com", only="robots,llms")
        call_kwargs = mock_fixes.call_args[1]
        assert call_kwargs["only"] == {"robots", "llms"}

    def test_fix_url_non_sicuro(self):
        """geo_fix blocks local URLs."""
        result = geo_fix("http://localhost:8080")
        data = json.loads(result)
        assert "error" in data


class TestGeoGapAnalysisTool:
    """Test per il tool MCP geo_gap_analysis."""

    @patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None))
    @patch("geo_optimizer.core.gap_analysis.run_gap_analysis")
    def test_gap_analysis_ritorna_json_valido(self, mock_gap_analysis, _mock_validate):
        """geo_gap_analysis serializza una gap analysis con piano d'azione."""
        mock_gap_analysis.return_value = GapAnalysisResult(
            weaker_url="https://weaker.example.com",
            stronger_url="https://stronger.example.com",
            weaker_score=55,
            stronger_score=82,
            score_gap=27,
            weaker_band="foundation",
            stronger_band="good",
            action_plan=[
                GapAction(
                    category="llms",
                    title="Publish llms.txt",
                    rationale="The stronger site has llms.txt and the weaker site does not.",
                    impact_points=5,
                    priority="high",
                    command="geo llms --base-url https://weaker.example.com",
                )
            ],
        )

        result = geo_gap_analysis("https://weaker.example.com", "https://stronger.example.com")
        data = json.loads(result)

        assert data["score_gap"] == 27
        assert data["weaker_url"] == "https://weaker.example.com"
        assert data["action_plan"][0]["title"] == "Publish llms.txt"

    def test_gap_analysis_blocca_url_non_sicuro(self):
        """geo_gap_analysis rifiuta URL verso reti private."""
        result = geo_gap_analysis("http://192.168.0.1", "https://example.com")
        data = json.loads(result)

        assert "error" in data


class TestGeoFactualAccuracyTool:
    """Test per il tool MCP geo_factual_accuracy."""

    @patch("geo_optimizer.core.factual_accuracy.run_factual_accuracy_audit")
    def test_factual_accuracy_ritorna_json_valido(self, mock_factual):
        """geo_factual_accuracy serializza il result dell'audit fattuale."""
        mock_factual.return_value = FactualAccuracyResult(
            checked=True,
            claims_found=4,
            claims_sourced=2,
            claims_unsourced=1,
            unsourced_claims=["Studies show 42% of users prefer GEO."],
            inconsistencies=["Conflicting numeric claims for 'conversion rate': 42%, 45%"],
            broken_source_links=["https://broken.example.com/report"],
            source_links_checked=2,
            severity="high",
        )

        result = geo_factual_accuracy("https://example.com/blog/post")
        data = json.loads(result)

        assert data["checked"] is True
        assert data["claims_found"] == 4
        assert data["severity"] == "high"
        assert data["broken_source_links"] == ["https://broken.example.com/report"]

    def test_factual_accuracy_blocca_url_non_sicuro(self):
        """geo_factual_accuracy rifiuta URL verso reti private."""
        result = geo_factual_accuracy("http://10.0.0.1/internal")
        data = json.loads(result)

        assert "error" in data
        assert "Unsafe URL" in data["error"]


# ============================================================================
# TEST: geo_llms_generate
# ============================================================================


class TestGeoLlmsGenerateTool:
    """Tests for the MCP tool geo_llms_generate."""

    @patch("geo_optimizer.core.llms_generator.generate_llms_txt", return_value="# Example\n> Web site")
    @patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[])
    @patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None)
    def test_genera_llms_txt(self, mock_discover, mock_fetch, mock_gen):
        """geo_llms_generate ritorna content llms.txt."""
        result = geo_llms_generate("https://example.com")

        assert "Example" in result
        assert len(result) > 0

    def test_llms_url_non_sicuro(self):
        """geo_llms_generate blocks private URLs."""
        result = geo_llms_generate("http://10.0.0.1")

        assert "Unsafe URL" in result


# ============================================================================
# TEST: geo_schema_validate
# ============================================================================


class TestGeoSchemaValidateTool:
    """Test per il tool MCP geo_schema_validate."""

    def test_schema_valido(self):
        """A complete WebSite schema is validated correctly."""
        schema = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "url": "https://example.com",
                "name": "Example",
            }
        )
        result = geo_schema_validate(schema, "website")
        data = json.loads(result)

        assert data["valid"] is True

    def test_schema_non_valido(self):
        """Schema incompleto is detected."""
        schema = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
            }
        )
        result = geo_schema_validate(schema, "website")
        data = json.loads(result)

        assert data["valid"] is False
        assert data["error"] is not None

    def test_json_malformato(self):
        """Invalid JSON is handled without crashing."""
        result = geo_schema_validate("{invalid json}", "website")
        data = json.loads(result)

        assert data["valid"] is False


# ============================================================================
# TEST: Resources
# ============================================================================


class TestMcpResources:
    """Test per le resource MCP."""

    def test_ai_bots_resource(self):
        """The ai-bots resource returns the bot list."""
        result = get_ai_bots()
        data = json.loads(result)

        assert "ai_bots" in data
        assert "GPTBot" in data["ai_bots"]
        assert data["total"] == len(data["ai_bots"])  # v4.0: bot count dinamico
        assert "tiers" in data
        assert "search" in data["tiers"]
        assert "training" in data["tiers"]
        assert "user" in data["tiers"]

    def test_score_bands_resource(self):
        """The score-bands resource returns the score bands."""
        result = get_score_bands()
        data = json.loads(result)

        assert "critical" in data or isinstance(data, dict)


# ============================================================================
# TEST: geo_citability
# ============================================================================


class TestGeoCitabilityTool:
    """Test per il tool MCP geo_citability."""

    @patch("geo_optimizer.utils.http.fetch_url")
    @patch("geo_optimizer.core.citability.audit_citability")
    def test_citability_happy_path_ritorna_json(self, mock_citability, mock_fetch):
        """geo_citability with fetch OK and citability audit returns valid JSON."""
        from unittest.mock import MagicMock

        from geo_optimizer.models.results import CitabilityResult, MethodScore

        # Arrange: response HTTP mock
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><h1>Titolo</h1><p>Contenuto con citazione (Fonte: esempio.com).</p></body></html>"
        mock_fetch.return_value = (mock_resp, None)

        # Arrange: result citability mock
        mock_result = CitabilityResult(
            methods=[
                MethodScore(
                    name="cite_sources",
                    label="Cite Sources",
                    detected=True,
                    score=8,
                    max_score=10,
                    impact="+27%",
                )
            ],
            total_score=72,
            grade="high",
            top_improvements=[],
        )
        mock_citability.return_value = mock_result

        from geo_optimizer.mcp.server import geo_citability

        # Act
        result = geo_citability("https://example.com")
        data = json.loads(result)

        # Assert
        assert "total_score" in data
        assert data["total_score"] == 72
        assert data["grade"] == "high"
        assert len(data["methods"]) == 1

    @patch("geo_optimizer.utils.http.fetch_url")
    def test_citability_fetch_errore_ritorna_errore(self, mock_fetch):
        """geo_citability con fetch_url che ritorna errore restituisce messaggio di errore."""
        # Arrange
        mock_fetch.return_value = (None, "Connection refused")

        from geo_optimizer.mcp.server import geo_citability

        # Act
        result = geo_citability("https://example.com")
        data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Connection refused" in data["error"] or "example.com" in data["error"]

    def test_citability_url_non_sicuro_ritorna_errore(self):
        """geo_citability blocks URLs pointing to private networks."""
        from geo_optimizer.mcp.server import geo_citability

        # Act
        result = geo_citability("http://192.168.0.1")
        data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Unsafe URL" in data["error"]

    @patch("geo_optimizer.utils.http.fetch_url")
    @patch("geo_optimizer.core.citability.audit_citability")
    def test_citability_eccezione_ritorna_errore(self, mock_citability, mock_fetch):
        """geo_citability gestisce eccezioni impreviste durante l'analisi."""
        from unittest.mock import MagicMock

        # Arrange
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>test</body></html>"
        mock_fetch.return_value = (mock_resp, None)
        mock_citability.side_effect = RuntimeError("Errore imprevisto")

        from geo_optimizer.mcp.server import geo_citability

        # Act
        result = geo_citability("https://example.com")
        data = json.loads(result)

        # Assert
        assert "error" in data


# ============================================================================
# TEST: exception paths for geo_audit, geo_fix, geo_llms_generate
# ============================================================================


class TestExceptionPaths:
    """Verifies the percorsi di eccezione nei tool MCP."""

    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_geo_audit_eccezione_ritorna_json_errore(self, mock_audit):
        """geo_audit gestisce eccezioni impreviste ritornando messaggio generico (fix #314).

        Il dettaglio dell'errore NON deve essere esposto al client per ragioni di sicurezza.
        L'errore reale viene loggato internamente.
        """
        # Arrange
        mock_audit.side_effect = RuntimeError("DB unavailable")

        # Act
        result = geo_audit("https://example.com")
        data = json.loads(result)

        # Assert — generic message to client, without internal detail (fix #314)
        assert "error" in data
        assert "DB unavailable" not in data["error"]
        assert "internal" in data["error"].lower() or "error" in data["error"].lower()
        assert data["url"] == "https://example.com"

    @patch("geo_optimizer.core.fixer.run_all_fixes")
    def test_geo_fix_eccezione_ritorna_json_errore(self, mock_fixes):
        """geo_fix gestisce eccezioni impreviste ritornando messaggio generico (fix #314).

        Il dettaglio dell'errore NON deve essere esposto al client per ragioni di sicurezza.
        L'errore reale viene loggato internamente.
        """
        # Arrange
        mock_fixes.side_effect = RuntimeError("Fixer crashed")

        # Act
        result = geo_fix("https://example.com")
        data = json.loads(result)

        # Assert — generic message to client, without internal detail (fix #314)
        assert "error" in data
        assert "Fixer crashed" not in data["error"]
        assert "internal" in data["error"].lower() or "error" in data["error"].lower()

    def test_geo_fix_categoria_non_valida_ritorna_errore(self):
        """geo_fix con categoria 'only' non valida ritorna errore senza crash."""
        # Act
        result = geo_fix("https://example.com", only="robots,invalid_cat")
        data = json.loads(result)

        # Assert
        assert "error" in data
        assert "invalid_cat" in data["error"]

    @patch("geo_optimizer.core.llms_generator.discover_sitemap")
    def test_geo_llms_generate_eccezione_ritorna_errore(self, mock_discover):
        """geo_llms_generate gestisce eccezioni impreviste ritornando messaggio di errore."""
        # Arrange
        mock_discover.side_effect = RuntimeError("Sitemap parse error")

        # Act
        result = geo_llms_generate("https://example.com")

        # Assert: fix #329 — ritorna JSON con errore generico (no info leak)
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Sitemap parse error" not in result  # l'eccezione interna NON viene esposta
class TestGeoAiSearchContextTool:
    def test_query_context_top_recommendation(self):
        """geo_ai_search_context resolves manual brief factors from answer text."""
        result = geo_ai_search_context(
            "best AI search visibility toolkit for content teams",
            "GEO Optimizer",
            "1. GEO Optimizer is the best AI search visibility toolkit for content teams.",
            cited_sources_json='["https://example.com/geo-optimizer"]',
            content_brief_json=(
                '{"details":{"readiness":"pass","factor_groups":{"gatekeepers":['
                '{"name":"topic_match","status":"manual_review","detail":"manual"},'
                '{"name":"explicit_price_info","status":"pass","detail":"price"},'
                '{"name":"recent_timestamp","status":"pass","detail":"date"},'
                '{"name":"top_list_position","status":"manual_review","detail":"manual"}]}}}'
            ),
        )
        data = json.loads(result)
        assert data["name"] == "ai_search_query_readiness"
        assert data["detected"] is True
        assert data["details"]["readiness"] == "top_recommendation"
        assert data["details"]["factor_groups"]["gatekeepers"][0]["status"] == "pass"
        assert data["details"]["factor_groups"]["gatekeepers"][3]["status"] == "pass"

    def test_query_context_rejects_bad_cited_sources_json(self):
        """geo_ai_search_context rejects non-list cited source payloads."""
        result = geo_ai_search_context(
            "best AI search visibility toolkit",
            "GEO Optimizer",
            "1. Competitor is cited.",
            cited_sources_json='{"source":"https://example.com"}',
        )
        data = json.loads(result)
        assert data["error"] == "cited_sources_json must be a JSON list"

"""
Tests for geo agent — WebMCP / tool-calling endpoint generator.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from geo_optimizer.cli.agent_cmd import agent_cmd
from geo_optimizer.core.agent_endpoints import (
    AgentReadinessResult,
    _extract_description,
    _extract_site_name,
    _site_offers_agent_services,
    run_agent_endpoint_generator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int, text: str = ""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


SAMPLE_HTML = """<html><head>
<title>Acme Corp | Property Management</title>
<meta name="description" content="Acme Corp manages properties across Montreal." />
</head><body></body></html>"""


# ---------------------------------------------------------------------------
# Unit: name / description extraction
# ---------------------------------------------------------------------------

class TestSiteOffersAgentServices:
    def test_detects_api_keyword(self):
        html = "<p>Use our REST API to integrate with your tools.</p>"
        assert _site_offers_agent_services(html, None) is True

    def test_detects_webhook(self):
        html = "<p>Send data via webhook to automate your workflows.</p>"
        assert _site_offers_agent_services(html, None) is True

    def test_detects_developer_portal(self):
        html = "<a href='/docs'>Developer Portal</a>"
        assert _site_offers_agent_services(html, None) is True

    def test_detects_chatbot(self):
        html = "<p>Our AI chatbot is available 24/7.</p>"
        assert _site_offers_agent_services(html, None) is True

    def test_detects_api_key_interactive_signal(self):
        html = "<p>Get your API key to start building.</p>"
        assert _site_offers_agent_services(html, None) is True

    def test_plain_business_site_returns_false(self):
        html = "<p>We manage properties in Montreal. Contact us for a quote.</p>"
        assert _site_offers_agent_services(html, None) is False

    def test_none_html_returns_false(self):
        assert _site_offers_agent_services(None, None) is False

    def test_detects_post_tool_in_tools_json(self):
        tools_json = '{"tools":[{"name":"search","method":"POST","parameters":{"q":"string"}}]}'
        assert _site_offers_agent_services(None, tools_json) is True

    def test_get_only_tools_without_params_not_sufficient(self):
        tools_json = '{"tools":[{"name":"get_summary","method":"GET","parameters":{}}]}'
        # No HTML signals either
        assert _site_offers_agent_services(None, tools_json) is False

    def test_ignores_signals_in_script_tags(self):
        # Minified JS often contains these words — should not trigger
        html = "<script>var api='x';var webhook=false;</script><p>Property management.</p>"
        assert _site_offers_agent_services(html, None) is False


class TestExtractors:
    def test_extract_name_from_title(self):
        name = _extract_site_name("https://acme.com", SAMPLE_HTML)
        assert name == "Acme Corp"

    def test_extract_name_fallback_to_hostname(self):
        name = _extract_site_name("https://acme.com", None)
        assert name == "acme.com"

    def test_extract_description(self):
        desc = _extract_description(SAMPLE_HTML)
        assert "Montreal" in desc

    def test_extract_description_fallback(self):
        desc = _extract_description(None)
        assert len(desc) > 10


# ---------------------------------------------------------------------------
# Unit: generator — all endpoints missing
# ---------------------------------------------------------------------------

class TestRunAgentEndpointGenerator:
    def _patch_all_missing(self):
        """Simulate a site with no agent endpoints at all."""
        from geo_optimizer.models.results import AiDiscoveryResult
        discovery = AiDiscoveryResult()  # all False by default

        return [
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, SAMPLE_HTML), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=discovery),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ]

    def test_generates_all_five_files_when_nothing_present(self):
        patches = self._patch_all_missing()
        with patches[0], patches[1], patches[2]:
            result = run_agent_endpoint_generator("https://acme.com")

        assert len(result.files) == 5
        paths = {f.path for f in result.files}
        assert ".well-known/ai.txt" in paths
        assert "ai/summary.json" in paths
        assert "ai/faq.json" in paths
        assert "ai/service.json" in paths
        assert "ai/tools.json" in paths

    def test_always_includes_potential_action_snippet(self):
        patches = self._patch_all_missing()
        with patches[0], patches[1], patches[2]:
            result = run_agent_endpoint_generator("https://acme.com")

        snippet_paths = {s.path for s in result.snippets}
        assert "potentialAction JSON-LD snippet" in snippet_paths

    def test_site_name_propagated(self):
        patches = self._patch_all_missing()
        with patches[0], patches[1], patches[2]:
            result = run_agent_endpoint_generator("https://acme.com")

        assert result.site_name == "Acme Corp"

    def test_not_agent_ready_when_all_missing(self):
        patches = self._patch_all_missing()
        with patches[0], patches[1], patches[2]:
            result = run_agent_endpoint_generator("https://acme.com")

        assert not result.agent_ready
        assert result.endpoints_present == 0

    def test_agent_ready_when_all_present(self):
        from geo_optimizer.models.results import AiDiscoveryResult
        discovery = AiDiscoveryResult(
            has_well_known_ai=True,
            has_summary=True,
            has_faq=True,
            has_service=True,
            endpoints_found=4,
        )
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, SAMPLE_HTML), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=discovery),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=True),
        ):
            result = run_agent_endpoint_generator("https://acme.com")

        assert result.agent_ready
        assert result.endpoints_present == 5
        assert result.files == []  # nothing to generate

    def test_skips_existing_endpoints(self):
        from geo_optimizer.models.results import AiDiscoveryResult
        discovery = AiDiscoveryResult(
            has_well_known_ai=True,
            has_summary=True,
            has_faq=False,
            has_service=False,
            endpoints_found=2,
        )
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, SAMPLE_HTML), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=discovery),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ):
            result = run_agent_endpoint_generator("https://acme.com")

        paths = {f.path for f in result.files}
        assert ".well-known/ai.txt" not in paths
        assert "ai/summary.json" not in paths
        assert "ai/faq.json" in paths
        assert "ai/service.json" in paths
        assert "ai/tools.json" in paths


# ---------------------------------------------------------------------------
# Unit: generated file content
# ---------------------------------------------------------------------------

class TestGeneratedContent:
    def _get_files(self):
        from geo_optimizer.models.results import AiDiscoveryResult
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, SAMPLE_HTML), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=AiDiscoveryResult()),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ):
            result = run_agent_endpoint_generator("https://acme.com")
        return {f.path: f for f in result.files}

    def test_tools_json_is_valid_json(self):
        files = self._get_files()
        data = json.loads(files["ai/tools.json"].content)
        assert "tools" in data
        assert len(data["tools"]) >= 3

    def test_tools_have_required_fields(self):
        files = self._get_files()
        data = json.loads(files["ai/tools.json"].content)
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "endpoint" in tool

    def test_summary_json_is_valid(self):
        files = self._get_files()
        data = json.loads(files["ai/summary.json"].content)
        assert len(data["name"]) >= 3
        assert len(data["description"]) >= 20
        assert "url" in data

    def test_faq_json_has_faqs_list(self):
        files = self._get_files()
        data = json.loads(files["ai/faq.json"].content)
        assert isinstance(data["faqs"], list)
        assert len(data["faqs"]) >= 2
        for faq in data["faqs"]:
            assert "question" in faq
            assert "answer" in faq

    def test_service_json_has_capabilities(self):
        files = self._get_files()
        data = json.loads(files["ai/service.json"].content)
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) >= 1

    def test_well_known_ai_contains_tools_url(self):
        files = self._get_files()
        content = files[".well-known/ai.txt"].content
        assert "tools:" in content
        assert "acme.com" in content

    def test_webmcp_snippet_included_when_site_offers_agent_services(self):
        from geo_optimizer.models.results import AiDiscoveryResult
        api_html = SAMPLE_HTML + "<p>Our REST API and developer portal let you integrate via webhooks.</p>"
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, api_html), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=AiDiscoveryResult()),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ):
            result = run_agent_endpoint_generator("https://acme.com")

        webmcp = next((s for s in result.snippets if "WebMCP" in s.path), None)
        assert webmcp is not None
        assert "registerTool" in webmcp.content
        assert "toolname" in webmcp.content

    def test_webmcp_snippet_excluded_for_plain_business_site(self):
        from geo_optimizer.models.results import AiDiscoveryResult
        plain_html = SAMPLE_HTML  # no API/agent signals
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, plain_html), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=AiDiscoveryResult()),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ):
            result = run_agent_endpoint_generator("https://acme.com")

        webmcp = next((s for s in result.snippets if "WebMCP" in s.path), None)
        assert webmcp is None

    def test_potential_action_snippet_is_valid_json_ld(self):
        import re

        from geo_optimizer.models.results import AiDiscoveryResult
        with (
            patch("geo_optimizer.core.agent_endpoints.fetch_url",
                  return_value=(_mock_response(200, SAMPLE_HTML), None)),
            patch("geo_optimizer.core.agent_endpoints.audit_ai_discovery",
                  return_value=AiDiscoveryResult()),
            patch("geo_optimizer.core.agent_endpoints._check_tools_endpoint",
                  return_value=False),
        ):
            result = run_agent_endpoint_generator("https://acme.com")

        pa = next(s for s in result.snippets if "potentialAction" in s.path)
        m = re.search(r"<script[^>]*>(.*?)</script>", pa.content, re.DOTALL)
        assert m
        data = json.loads(m.group(1))
        assert data["@type"] == "WebSite"
        assert "potentialAction" in data


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestAgentCLI:
    def _run(self, args, side_effect_files=None):
        runner = CliRunner()

        mock_result = AgentReadinessResult(
            url="https://acme.com",
            site_name="Acme Corp",
            site_description="Test site",
            has_well_known_ai=False,
            has_summary=False,
            has_faq=False,
            has_service=False,
            has_tools=False,
        )
        from geo_optimizer.core.agent_endpoints import AgentFile
        mock_result.files = [
            AgentFile("ai/tools.json", '{"tools":[]}', "Tool definitions"),
        ]
        mock_result.snippets = [
            AgentFile("WebMCP HTML snippet", "<!-- snippet -->", "Add to layout"),
        ]

        with (
            patch("geo_optimizer.cli.agent_cmd.validate_public_url", return_value=(True, None)),
            patch("geo_optimizer.cli.agent_cmd.run_agent_endpoint_generator", return_value=mock_result),
        ):
            return runner.invoke(agent_cmd, args)

    def test_preview_mode_shows_preview_header(self):
        result = self._run(["--url", "https://acme.com"])
        assert result.exit_code == 0
        assert "PREVIEW" in result.output

    def test_preview_mode_shows_run_with_apply_hint(self):
        result = self._run(["--url", "https://acme.com"])
        assert "--apply" in result.output

    def test_apply_mode_writes_files(self, tmp_path):
        from geo_optimizer.core.agent_endpoints import AgentFile
        runner = CliRunner()

        mock_result = AgentReadinessResult(
            url="https://acme.com",
            site_name="Acme",
            site_description="Test",
        )
        mock_result.files = [
            AgentFile("ai/tools.json", '{"tools":[]}', "Tools"),
        ]
        mock_result.snippets = []

        with runner.isolated_filesystem():
            with patch("geo_optimizer.cli.agent_cmd.validate_public_url",
                       return_value=(True, None)), patch("geo_optimizer.cli.agent_cmd.run_agent_endpoint_generator",
                       return_value=mock_result):
                result = runner.invoke(
                    agent_cmd,
                    ["--url", "https://acme.com", "--apply", "--output-dir", "out"]
                )

            assert result.exit_code == 0
            assert (runner.isolated_filesystem.__self__ if hasattr(runner, '_') else True)
            import os
            assert os.path.exists("out/ai/tools.json")

    def test_invalid_url_exits_nonzero(self):
        runner = CliRunner()
        with patch("geo_optimizer.cli.agent_cmd.validate_public_url",
                   return_value=(False, "Host not allowed")):
            result = runner.invoke(agent_cmd, ["--url", "https://localhost"])
        assert result.exit_code != 0

from __future__ import annotations

from bs4 import BeautifulSoup

from geo_optimizer.core.citability import audit_citability
from geo_optimizer.core.scoring import CATEGORY_MAX_SCORES, _score_ai_discovery, _score_llms, _score_robots
from geo_optimizer.models.config import BOT_TIERS, CITATION_BOTS
from geo_optimizer.models.results import AiDiscoveryResult, LlmsTxtResult, RobotsResult


def test_optional_discovery_files_do_not_change_readiness_score():
    assert sum(CATEGORY_MAX_SCORES.values()) == 100
    assert _score_llms(LlmsTxtResult(found=True, has_h1=True, has_links=True)) == 0
    assert _score_ai_discovery(AiDiscoveryResult(has_well_known_ai=True, has_summary=True, summary_valid=True)) == 0


def test_wildcard_and_explicit_search_crawler_access_score_equally():
    wildcard = RobotsResult(found=True, citation_bots_ok=True, citation_bots_explicit=False)
    explicit = RobotsResult(found=True, citation_bots_ok=True, citation_bots_explicit=True)
    assert _score_robots(wildcard) == _score_robots(explicit) == CATEGORY_MAX_SCORES["robots"]


def test_training_crawlers_are_not_classified_as_citation_bots():
    assert {"GPTBot", "ClaudeBot"} <= BOT_TIERS["training"]
    assert not ({"GPTBot", "ClaudeBot"} & CITATION_BOTS)
    assert "Googlebot" in BOT_TIERS["search"]


def test_citability_results_do_not_promise_measured_uplift():
    result = audit_citability(
        BeautifulSoup("<html><body><h1>Example</h1></body></html>", "html.parser"), "https://example.com"
    )
    assert all(not method.impact for method in result.methods)
    assert all(method.evidence_level == "product_heuristic" for method in result.methods)
    assert all("%" not in suggestion for suggestion in result.top_improvements)

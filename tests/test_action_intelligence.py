from __future__ import annotations

from geo_optimizer.core.action_intelligence import build_next_actions


def test_next_actions_use_category_specific_recommendation_mapping():
    score_breakdown = {
        "llms": 14,  # gap 4
        "robots": 15,  # gap 3
        "schema": 13,  # gap 3
        "brand_entity": 7,  # gap 3
        "meta": 14,
        "content": 12,
        "signals": 6,
        "ai_discovery": 6,
    }
    recommendations = [
        "Add conversion CTAs: quote, consultation, or booking flow on key pages.",
        "Create /llms.txt for AI indexing and include key links.",
        "Update robots.txt to include all AI bots (GPTBot, ClaudeBot, PerplexityBot)",
        "Add FAQPage schema with site FAQs",
        "Add sameAs links in Organization schema to Wikipedia, Wikidata, LinkedIn, or Crunchbase for Knowledge Graph disambiguation",
    ]

    actions = build_next_actions(score_breakdown, recommendations, max_items=4)
    by_key = {a.key: a for a in actions}

    assert "llms" in by_key
    assert "robots" in by_key
    assert "schema" in by_key
    assert "brand_entity" in by_key

    assert "llms.txt" in by_key["llms"].why.lower()
    assert "robots.txt" in by_key["robots"].why.lower()
    assert "schema" in by_key["schema"].why.lower()
    assert ("knowledge graph" in by_key["brand_entity"].why.lower()) or ("sameas" in by_key["brand_entity"].why.lower())


def test_next_actions_fallback_uses_category_defaults_not_indexed_recommendations():
    score_breakdown = {
        "llms": 10,
        "robots": 10,
        "schema": 10,
    }
    recommendations = ["Add conversion CTAs: quote, consultation, or booking flow on key pages."]

    actions = build_next_actions(score_breakdown, recommendations, max_items=3)
    by_key = {a.key: a for a in actions}

    assert "llms.txt" in by_key["llms"].why.lower()
    assert "robots.txt" in by_key["robots"].why.lower()
    assert "json-ld" in by_key["schema"].why.lower()

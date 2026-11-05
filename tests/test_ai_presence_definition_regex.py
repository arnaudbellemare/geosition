"""Regression: AI presence definition + attribution patterns (EN/FR)."""

from __future__ import annotations

from geo_optimizer.core.audit_marketing.analysis import _ATTRIBUTED_STAT_RE, _DEFINITION_BLOCK_RE


def test_definition_block_french_firm_tagline():
    s = (
        "Gestion Velora est une société de gestion immobilière à Montréal "
        "qui accompagne les syndicats et les bailleurs."
    )
    assert _DEFINITION_BLOCK_RE.search(s)


def test_definition_block_english():
    s = "Acme Corp is a property management company serving landlords in Montreal."
    assert _DEFINITION_BLOCK_RE.search(s)


def test_attribution_french_selon():
    t = "Selon la SCHL (2023), la hausse des loyers a atteint 5,2% sur un an."
    assert _ATTRIBUTED_STAT_RE.search(t)


def test_attribution_parenthetical_year():
    t = "Les copropriétés ont augmenté (Statistique Canada, 2022) de 12% en cinq ans."
    assert _ATTRIBUTED_STAT_RE.search(t)

"""Regression tests for marketing audit guidance."""

from __future__ import annotations

from bs4 import BeautifulSoup

from geo_optimizer.core.audit_marketing.analysis import audit_content_strategy, audit_copywriting, audit_images


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_generic_marketing_guidance_does_not_emit_property_examples():
    soup = _soup(
        """
        <html>
          <head><title>Acme AI Reports</title></head>
          <body>
            <h1>AI audit software</h1>
            <h2>Overview</h2>
            <img src="/static/dashboard.png" alt="photo">
            <a href="/features/">Features</a>
          </body>
        </html>
        """
    )

    copy = audit_copywriting(soup, vertical="saas-technology", page_keyword="AI audit software")
    images = audit_images(soup, base_url="https://example.com", page_keyword="AI audit software", vertical="saas-technology")
    strategy = audit_content_strategy(soup, base_url="https://example.com", vertical="saas-technology")

    text = " ".join(copy.suggestions + images.suggestions + strategy.suggestions)
    forbidden = ("Gestion Velora", "copropriété", "Airbnb", "gestion-locative", "syndicat-copropriete")
    assert not any(term in text for term in forbidden)

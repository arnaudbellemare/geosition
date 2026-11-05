"""Tests for audit_sxo module."""
from bs4 import BeautifulSoup

from geo_optimizer.core.audit_sxo import audit_sxo


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_transactional_url_transactional_content():
    body = "contact us get a quote book a service sign up free quote"
    soup = _soup(f"<html><body><p>{body}</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/pricing")
    assert result.checked is True
    assert "transactional" in result.url_intent_signals
    assert "transactional" in result.content_intent_signals
    assert result.intent_aligned is True
    assert result.sxo_score >= 2


def test_informational_url_informational_content():
    body = (
        "In this guide you will learn how to manage a condo. "
        "This article covers what is required step by step."
    )
    soup = _soup(f"<html><body><p>{body}</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/guide/property-management")
    assert "informational" in result.url_intent_signals
    assert "informational" in result.content_intent_signals
    assert result.intent_aligned is True


def test_mismatch_transactional_url_informational_content():
    body = (
        "In this guide you will learn what is condo management. "
        "This article explains how to and why step by step overview."
    )
    soup = _soup(f"<html><body><p>{body}</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/pricing")
    assert result.mismatch_type == "transactional_url_informational_content"
    assert len(result.recommendations) > 0


def test_no_url_signal_short_content():
    soup = _soup("<html><body><p>Hello world</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/home")
    assert result.intent_aligned is True
    assert result.matched_intent == "unclear"


def test_no_url_signal_long_content():
    body = " ".join(["word"] * 350)
    soup = _soup(f"<html><body><p>{body}</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/home")
    assert result.intent_aligned is True
    assert result.matched_intent == "informational"


def test_commercial_url_commercial_content():
    body = "pros and cons vs. compared to our rating stars out of 5 avantages inconvénients"
    soup = _soup(f"<html><body><p>{body}</p></body></html>")
    result = audit_sxo(soup, url="https://example.com/compare/airbnb-vs-traditional")
    assert "commercial" in result.url_intent_signals
    assert "commercial" in result.content_intent_signals
    assert result.intent_aligned is True


def test_checked_flag_set():
    soup = _soup("<html><body></body></html>")
    result = audit_sxo(soup, url="")
    assert result.checked is True

"""Tests for audit_indexnow module."""
from bs4 import BeautifulSoup

from geo_optimizer.core.audit_indexnow import audit_indexnow


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_no_indexnow_signals():
    soup = _soup("<html><head></head><body></body></html>")
    result = audit_indexnow(soup)
    assert result.checked is True
    assert result.is_configured is False
    assert result.has_meta_tag is False
    assert result.has_link_element is False
    assert any("IndexNow not detected" in r for r in result.recommendations)


def test_valid_meta_tag():
    key = "a" * 32  # valid 32-char hex key
    soup = _soup(f'<html><head><meta name="indexnow-key" content="{key}"></head></html>')
    result = audit_indexnow(soup, base_url="https://example.com")
    assert result.has_meta_tag is True
    assert result.is_configured is True
    assert result.key_looks_valid is True
    assert result.key_value == key
    assert result.key_url == f"https://example.com/{key}.txt"


def test_invalid_key_format():
    key = "not-a-valid-key"
    soup = _soup(f'<html><head><meta name="indexnow-key" content="{key}"></head></html>')
    result = audit_indexnow(soup)
    assert result.has_meta_tag is True
    assert result.key_looks_valid is False
    assert any("doesn't match expected format" in r for r in result.recommendations)


def test_link_element_detected():
    soup = _soup('<html><head><link rel="indexnow" href="https://example.com/abc.txt"></head></html>')
    result = audit_indexnow(soup)
    assert result.has_link_element is True
    assert result.is_configured is True
    assert result.key_url == "https://example.com/abc.txt"


def test_indexnow_meta_name_variant():
    key = "b" * 64
    soup = _soup(f'<html><head><meta name="indexnow" content="{key}"></head></html>')
    result = audit_indexnow(soup)
    assert result.has_meta_tag is True
    assert result.key_looks_valid is True

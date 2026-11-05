"""Tests for Semantic Coherence Analysis (#253)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from geo_optimizer.core.coherence_analyzer import analyze_coherence
from geo_optimizer.core.term_extractor import extract_page_terms
from geo_optimizer.models.results import PageTermExtract


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ─── Term Extractor ──────────────────────────────────────────────────────────


class TestTermExtractor:
    def test_extracts_title_and_h1(self):
        html = "<html><head><title>My Page</title></head><body><h1>Welcome</h1></body></html>"
        result = extract_page_terms(_soup(html), url="https://example.com")
        assert result.title == "My Page"
        assert result.h1 == "Welcome"
        assert result.url == "https://example.com"

    def test_extracts_language(self):
        html = '<html lang="en"><head><title>T</title></head><body></body></html>'
        result = extract_page_terms(_soup(html))
        assert result.language == "en"

    def test_extracts_definitions(self):
        html = "<html><body><p>Machine Learning is a subset of artificial intelligence.</p></body></html>"
        result = extract_page_terms(_soup(html))
        assert len(result.definitions) >= 1
        assert "Machine Learning" in result.definitions[0]

    def test_extracts_key_terms(self):
        html = "<html><body><p>Google Cloud and Google Cloud are used. Amazon Web Services too.</p></body></html>"
        result = extract_page_terms(_soup(html))
        assert "Google Cloud" in result.key_terms

    def test_empty_body(self):
        result = extract_page_terms(_soup("<html><body></body></html>"))
        assert result.title == ""
        assert result.definitions == []

    def test_extracts_hreflang_langs(self):
        html = """<html lang="fr-CA"><head>
            <link rel="alternate" hreflang="fr-CA" href="https://example.com/" />
            <link rel="alternate" hreflang="en-CA" href="https://example.com/en/" />
            <link rel="alternate" hreflang="x-default" href="https://example.com/" />
        </head><body></body></html>"""
        result = extract_page_terms(_soup(html))
        assert "fr-ca" in result.hreflang_langs
        assert "en-ca" in result.hreflang_langs
        assert "x-default" in result.hreflang_langs

    def test_no_hreflang_gives_empty_list(self):
        html = "<html lang='en'><head><title>T</title></head><body></body></html>"
        result = extract_page_terms(_soup(html))
        assert result.hreflang_langs == []


# ─── Coherence Analyzer ─────────────────────────────────────────────────────


class TestCoherenceAnalyzer:
    def test_single_page_no_issues(self):
        result = analyze_coherence([PageTermExtract(url="https://a.com")])
        assert result.checked is True
        assert result.pages_analyzed == 1
        assert result.issues == []

    def test_no_issues_when_consistent(self):
        extracts = [
            PageTermExtract(url="https://a.com", title="About Us", language="en"),
            PageTermExtract(url="https://b.com", title="Services", language="en"),
        ]
        result = analyze_coherence(extracts)
        assert result.coherence_score == 100
        assert result.language_consistency == 1.0

    def test_detects_duplicate_titles(self):
        extracts = [
            PageTermExtract(url="https://a.com/page1", title="Our Amazing Services"),
            PageTermExtract(url="https://a.com/page2", title="Our Amazing Services"),
        ]
        result = analyze_coherence(extracts)
        dup_issues = [i for i in result.issues if i.issue_type == "duplicate_title"]
        assert len(dup_issues) >= 1
        assert result.coherence_score < 100

    def test_detects_mixed_language(self):
        # Non-locale URLs, no hreflang — truly inconsistent, should be flagged
        extracts = [
            PageTermExtract(url="https://a.com/about", language="en"),
            PageTermExtract(url="https://a.com/contact", language="it"),
            PageTermExtract(url="https://a.com/services", language="en"),
        ]
        result = analyze_coherence(extracts)
        lang_issues = [i for i in result.issues if i.issue_type == "mixed_language"]
        assert len(lang_issues) >= 1
        assert result.language_consistency < 1.0

    def test_bilingual_hreflang_not_flagged(self):
        # hreflang covers both en and fr — intentional bilingual site, no issue
        hreflang = ["fr-ca", "en-ca", "x-default"]
        extracts = [
            PageTermExtract(url="https://example.com/", language="fr", hreflang_langs=hreflang),
            PageTermExtract(url="https://example.com/services", language="fr", hreflang_langs=hreflang),
            PageTermExtract(url="https://example.com/en/", language="en", hreflang_langs=hreflang),
            PageTermExtract(url="https://example.com/en/services", language="en", hreflang_langs=hreflang),
        ]
        result = analyze_coherence(extracts)
        lang_issues = [i for i in result.issues if i.issue_type == "mixed_language"]
        assert lang_issues == []

    def test_locale_prefix_url_not_flagged(self):
        # /en/ subdirectory pattern — intentional locale structure, no hreflang needed
        extracts = [
            PageTermExtract(url="https://example.com/", language="fr"),
            PageTermExtract(url="https://example.com/services", language="fr"),
            PageTermExtract(url="https://example.com/en/", language="en"),
            PageTermExtract(url="https://example.com/en/services", language="en"),
        ]
        result = analyze_coherence(extracts)
        lang_issues = [i for i in result.issues if i.issue_type == "mixed_language"]
        assert lang_issues == []

    def test_three_language_hreflang_not_flagged(self):
        # Three-language site with hreflang — all should pass silently
        hreflang = ["en", "fr", "de"]
        extracts = [
            PageTermExtract(url="https://a.com/", language="en", hreflang_langs=hreflang),
            PageTermExtract(url="https://a.com/fr/", language="fr", hreflang_langs=hreflang),
            PageTermExtract(url="https://a.com/de/", language="de", hreflang_langs=hreflang),
        ]
        result = analyze_coherence(extracts)
        lang_issues = [i for i in result.issues if i.issue_type == "mixed_language"]
        assert lang_issues == []

    def test_detects_conflicting_definitions(self):
        extracts = [
            PageTermExtract(
                url="https://a.com/page1",
                definitions=["Machine Learning is a subset of artificial intelligence."],
            ),
            PageTermExtract(
                url="https://a.com/page2",
                definitions=["Machine Learning is a statistical method for data analysis."],
            ),
        ]
        result = analyze_coherence(extracts)
        conflict_issues = [i for i in result.issues if i.issue_type == "conflicting_definition"]
        assert len(conflict_issues) >= 1
        assert result.coherence_score < 100

    def test_score_floor_at_zero(self):
        extracts = [
            PageTermExtract(url=f"https://a.com/{i}", title="Same Title", language="en")
            for i in range(25)
        ]
        result = analyze_coherence(extracts)
        assert result.coherence_score >= 0

    def test_empty_list(self):
        result = analyze_coherence([])
        assert result.checked is True
        assert result.pages_analyzed == 0

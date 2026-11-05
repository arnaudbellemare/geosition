"""Tests for audit_aeo module."""

from bs4 import BeautifulSoup

from geo_optimizer.core.audit_aeo import audit_aeo
from geo_optimizer.models.results import SchemaResult


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_no_signals_gives_recommendations():
    soup = _soup("<html><body><p>Short.</p></body></html>")
    result = audit_aeo(soup)
    assert result.checked is True
    assert result.featured_snippet_score == 0
    assert result.paa_score == 0
    assert len(result.recommendations) > 0


def test_paragraph_snippet_candidate():
    # 45-word paragraph
    text = " ".join(["word"] * 45)
    soup = _soup(f"<html><body><p>{text}</p></body></html>")
    result = audit_aeo(soup)
    assert result.has_paragraph_snippet_candidate is True
    assert result.snippet_candidate_word_count == 45


def test_list_snippet_candidate():
    soup = _soup("<html><body><ul><li>A</li><li>B</li><li>C</li></ul></body></html>")
    result = audit_aeo(soup)
    assert result.has_list_snippet_candidate is True
    assert result.list_snippet_item_count == 3


def test_table_snippet_candidate():
    soup = _soup(
        "<html><body><table>"
        "<tr><th>Name</th><th>Price</th></tr>"
        "<tr><td>A</td><td>10</td></tr>"
        "</table></body></html>"
    )
    result = audit_aeo(soup)
    assert result.has_table_snippet_candidate is True


def test_question_headings_detected():
    soup = _soup(
        "<html><body>"
        "<h2>What is property management?</h2>"
        "<h3>How does it work?</h3>"
        "</body></html>"
    )
    result = audit_aeo(soup)
    assert result.has_question_headings is True
    assert result.question_heading_count == 2


def test_faq_schema_detected():
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "Q1?", "acceptedAnswer": {"@type": "Answer", "text": "A1"}},
            {"@type": "Question", "name": "Q2?", "acceptedAnswer": {"@type": "Answer", "text": "A2"}},
        ],
    }

    class FakeSchema:
        schemas_found = [faq_schema]
        faq_item_count = 0

    soup = _soup("<html><body></body></html>")
    result = audit_aeo(soup, schema_result=FakeSchema())
    assert result.has_faq_schema is True
    assert result.faq_schema_item_count == 2


def test_faq_schema_detected_from_real_schema_result_raw_schemas_graph():
    schema = SchemaResult(
        raw_schemas=[
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "FAQPage",
                        "mainEntity": [
                            {"@type": "Question", "name": "Q1?", "acceptedAnswer": {"@type": "Answer", "text": "A1"}},
                            {"@type": "Question", "name": "Q2?", "acceptedAnswer": {"@type": "Answer", "text": "A2"}},
                        ],
                    },
                    {
                        "@type": "Organization",
                        "name": "Acme",
                        "telephone": "514-000-0000",
                        "address": {"@type": "PostalAddress", "streetAddress": "123 rue"},
                        "sameAs": ["https://www.wikidata.org/wiki/Q123"],
                    },
                ],
            }
        ]
    )

    result = audit_aeo(_soup("<html><body></body></html>"), schema_result=schema)
    assert result.has_faq_schema is True
    assert result.faq_schema_item_count == 2
    assert result.has_org_schema is True
    assert result.has_nap_consistency is True
    assert result.has_wikidata_link is True


def test_nap_consistency_from_org_schema():
    class FakeSchema:
        schemas_found = [
            {
                "@type": "Organization",
                "name": "Velora",
                "telephone": "514-000-0000",
                "address": {"@type": "PostalAddress", "streetAddress": "123 rue"},
            }
        ]
        faq_item_count = 0

    soup = _soup("<html><body></body></html>")
    result = audit_aeo(soup, schema_result=FakeSchema())
    assert result.has_org_schema is True
    assert result.has_nap_consistency is True


def test_full_featured_snippet_score():
    text = " ".join(["word"] * 50)
    soup = _soup(
        f"<html><body>"
        f"<p>{text}</p>"
        f"<ul><li>A</li><li>B</li><li>C</li></ul>"
        f"<table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr></table>"
        f"</body></html>"
    )
    result = audit_aeo(soup)
    assert result.featured_snippet_score == 3

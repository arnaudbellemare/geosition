from __future__ import annotations

from geo_optimizer.core.link_graph import analyze_link_graph_from_html_map


def test_link_graph_orphan_detection() -> None:
    urls = [
        "https://example.com",
        "https://example.com/services",
        "https://example.com/blog",
        "https://example.com/pricing",
    ]
    html_map = {
        "https://example.com": """
            <html><body>
              <a href="/services">Services</a>
              <a href="/blog">Blog</a>
            </body></html>
        """,
        "https://example.com/services": """
            <html><body><a href="/blog">Blog</a></body></html>
        """,
        "https://example.com/blog": """
            <html><body><a href="/services">Services</a></body></html>
        """,
        "https://example.com/pricing": """
            <html><body><p>No incoming links</p></body></html>
        """,
    }

    result = analyze_link_graph_from_html_map("https://example.com/sitemap.xml", urls, html_map)

    assert result.error == ""
    assert result.pages_discovered == 4
    assert "https://example.com/pricing" in result.orphan_pages
    assert result.internal_edges >= 3
    assert result.recommendations


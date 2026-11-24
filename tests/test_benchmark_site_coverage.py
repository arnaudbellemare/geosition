from unittest.mock import Mock, patch

from geo_optimizer.core.benchmark.runner import run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.audit import ContentResult, MetaResult


def test_benchmark_audits_relevant_same_site_sitemap_pages(tmp_path):
    sitemap = Mock(status_code=200, url="https://shop.example/sitemap.xml")
    sitemap.text = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://shop.example/about</loc></url>
    <url><loc>https://shop.example/compare/options</loc></url>
    <url><loc>https://other.example/compare</loc></url>
    </urlset>"""

    def audit(url, **kwargs):
        return AuditResult(url=url, meta=MetaResult(title_text="Compare options" if "/compare" in url else "About"),
                           content=ContentResult(h1_text="Compare options" if "/compare" in url else "About"))

    with patch("geo_optimizer.core.benchmark.runner.run_full_audit", side_effect=audit) as fetch, \
         patch("geo_optimizer.core.benchmark.runner.fetch_url", return_value=(sitemap, None), create=True):
        result = run_domain_benchmark("shop.example", answers=[{
            "prompt": "Compare options", "answer_text": "Example https://shop.example/compare/options",
            "provider": "chatgpt",
        }], store=BenchmarkStore(tmp_path / "bench.db"))

    urls = {page.url for page in result.page_coverage}
    assert "https://shop.example/compare/options" in urls
    assert all("other.example" not in call.args[0] for call in fetch.call_args_list)
    assert not any(gap.task == "comparison" for gap in result.task_gaps)


def test_comparison_pages_are_prioritized_and_sitemap_index_stays_on_site():
    from geo_optimizer.core.benchmark.runner import _site_pages

    index = Mock(status_code=200, url="https://shop.example/sitemap.xml")
    index.text = """<sitemapindex><sitemap><loc>https://other.example/sitemap.xml</loc></sitemap>
    <sitemap><loc>https://shop.example/pages.xml</loc></sitemap></sitemapindex>"""
    pages = Mock(status_code=200, url="https://shop.example/pages.xml")
    pages.text = "<urlset>" + "".join(
        f"<url><loc>https://shop.example/page-{i}</loc></url>" for i in range(8)
    ) + "<url><loc>https://shop.example/compare/options</loc></url></urlset>"
    with patch("geo_optimizer.core.benchmark.runner.fetch_url", side_effect=[(index, None), (pages, None)]) as fetch:
        selected = _site_pages("https://shop.example", {"comparison", "discovery"})
    assert selected[0] == "https://shop.example/compare/options"
    assert len(selected) == 4
    assert all("other.example" not in call.args[0] for call in fetch.call_args_list)

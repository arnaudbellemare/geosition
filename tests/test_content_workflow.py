from __future__ import annotations

from click.testing import CliRunner

from geo_optimizer.cli.content_cmd import content_cmd
from geo_optimizer.core.content_workflow import analyze_content_workflow_html


def test_content_workflow_html_target_keyword_density() -> None:
    html = """
    <html>
      <head>
        <title>Gestion Velora - Property Management</title>
        <link rel="canonical" href="https://example.com/services" />
      </head>
      <body>
        <a href="/about">About us</a>
        <a href="/services">Read more</a>
        <p>Gestion Velora is a property management company in Montreal.</p>
        <p>Our property management service improves property value and tenant retention.</p>
      </body>
    </html>
    """
    result = analyze_content_workflow_html(
        html=html,
        source="inline",
        base_url="https://example.com",
        target_keywords=["property management", "montreal"],
        top_terms=10,
    )

    assert result.error == ""
    assert result.analyzed_words > 0
    assert len(result.target_keywords) == 2
    assert result.target_keywords[0].keyword == "property management"
    assert any("Target keyword" in rec or "density" in rec for rec in result.recommendations)


def test_content_cmd_file_json_output(tmp_path) -> None:
    html_path = tmp_path / "page.html"
    html_path.write_text(
        "<html><body><p>Entity resolution and management content for testing.</p></body></html>",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        content_cmd,
        [
            "--file",
            str(html_path),
            "--keywords",
            "entity resolution",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"source"' in result.output
    assert '"target_keywords"' in result.output


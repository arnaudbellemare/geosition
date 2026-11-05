"""
Test per geo_optimizer.core.fixer e geo_optimizer.cli.fix_cmd.

Verifies the generazione di fix automatici (robots, llms, schema, meta)
e il comando CLI geo fix. Tutto mockato — zero calls HTTP.
"""

from unittest.mock import patch

from click.testing import CliRunner

from geo_optimizer.cli.main import cli
from geo_optimizer.core.fixer import (
    generate_content_rewrite_fix,
    generate_llms_fix,
    generate_meta_fix,
    generate_robots_fix,
    generate_schema_fix,
    generate_vertical_content_pack,
    generate_vertical_fix_templates,
    run_all_fixes,
)
from geo_optimizer.models.config import SAMEAS_AUTHORITATIVE_DOMAINS
from geo_optimizer.models.results import (
    AuditResult,
    ContentResult,
    FixItem,
    FixPlan,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
    VerticalAuditResult,
)

# ============================================================================
# FIXTURES
# ============================================================================


def _make_result(**overrides):
    """Creates a AuditResult con valori di default per i test."""
    result = AuditResult(
        url="https://example.com",
        score=30,
        band="critical",
        robots=RobotsResult(
            found=False,
        ),
        llms=LlmsTxtResult(
            found=False,
        ),
        schema=SchemaResult(
            found_types=[],
            has_website=False,
            has_faq=False,
            has_webapp=False,
        ),
        meta=MetaResult(
            has_title=False,
            has_description=False,
            has_canonical=False,
            has_og_title=False,
            has_og_description=False,
            has_og_image=False,
        ),
        content=ContentResult(
            has_h1=False,
        ),
        recommendations=["Add robots.txt", "Add llms.txt"],
    )
    for key, value in overrides.items():
        parts = key.split(".")
        obj = result
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
    return result


def _make_optimized_result():
    """Creates a AuditResult con tutto ottimizzato (no fix necessario)."""
    return _make_result(
        **{
            "score": 95,
            "band": "excellent",
            "robots.found": True,
            "robots.bots_allowed": ["GPTBot", "ClaudeBot", "PerplexityBot"],
            "robots.bots_missing": [],
            "robots.citation_bots_ok": True,
            "robots.citation_bots_explicit": True,
            "llms.found": True,
            "llms.has_h1": True,
            "llms.has_description": True,
            "llms.has_sections": True,
            "llms.has_links": True,
            "schema.has_website": True,
            "schema.has_faq": True,
            "schema.found_types": ["WebSite", "FAQPage", "Organization"],
            "meta.has_title": True,
            "meta.has_description": True,
            "meta.has_canonical": True,
            "meta.has_og_title": True,
            "meta.has_og_description": True,
            "meta.has_og_image": True,
            "content.has_h1": True,
            "content.has_numbers": True,
            "content.has_links": True,
            "content.word_count": 600,
            "content.has_heading_hierarchy": True,
            "content.has_lists_or_tables": True,
            "content.has_front_loading": True,
            "ai_discovery.has_well_known_ai": True,
            "ai_discovery.has_summary": True,
            "ai_discovery.summary_valid": True,
            "ai_discovery.has_faq": True,
            "ai_discovery.has_service": True,
            "ai_discovery.endpoints_found": 4,
        }
    )


# ============================================================================
# TEST: generate_robots_fix
# ============================================================================


class TestGenerateRobotsFix:
    """Test per la generazione di fix robots.txt."""

    def test_robots_non_trovato_genera_file_completo(self):
        """If robots.txt does not exist, generates a complete file with all bots."""
        result = _make_result()
        fix = generate_robots_fix(result, "https://example.com")

        assert fix is not None
        assert fix.category == "robots"
        assert fix.action == "create"
        assert fix.file_name == "robots.txt"
        assert "GPTBot" in fix.content
        assert "ClaudeBot" in fix.content
        assert "PerplexityBot" in fix.content
        assert "User-agent: *" in fix.content
        assert "Sitemap:" in fix.content

    def test_robots_con_bot_mancanti_genera_append(self):
        """If robots.txt exists but bots are missing, generates lines to append."""
        result = _make_result(
            **{
                "robots.found": True,
                "robots.bots_allowed": ["GPTBot"],
                "robots.bots_missing": ["ClaudeBot", "PerplexityBot"],
            }
        )
        fix = generate_robots_fix(result, "https://example.com")

        assert fix is not None
        assert fix.action == "append"
        assert "ClaudeBot" in fix.content
        assert "PerplexityBot" in fix.content
        assert "GPTBot" not in fix.content  # Già presente, non va aggiunto

    def test_robots_completo_ritorna_none(self):
        """Se tutti i bot sono già consentiti, non serve fix."""
        result = _make_result(
            **{
                "robots.found": True,
                "robots.bots_missing": [],
            }
        )
        fix = generate_robots_fix(result, "https://example.com")

        assert fix is None


# ============================================================================
# TEST: generate_llms_fix
# ============================================================================


class TestGenerateLlmsFix:
    """Test per la generazione di fix llms.txt."""

    @patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[])
    @patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None)
    def test_llms_non_trovato_genera_file(self, mock_discover, mock_fetch):
        """If llms.txt does not exist, generates a new file."""
        result = _make_result()
        fix = generate_llms_fix(result, "https://example.com")

        assert fix is not None
        assert fix.category == "llms"
        assert fix.action == "create"
        assert fix.file_name == "llms.txt"
        assert len(fix.content) > 0

    def test_llms_completo_ritorna_none(self):
        """Se llms.txt è già completo, non serve fix."""
        result = _make_result(
            **{
                "llms.found": True,
                "llms.has_h1": True,
                "llms.has_sections": True,
                "llms.has_links": True,
            }
        )
        fix = generate_llms_fix(result, "https://example.com")

        assert fix is None


# ============================================================================
# TEST: generate_schema_fix
# ============================================================================


class TestGenerateSchemaFix:
    """Test per la generazione di fix schema JSON-LD."""

    def test_schema_website_mancante(self):
        """Se manca WebSite schema, lo genera."""
        result = _make_result()
        fixes = generate_schema_fix(result, "https://example.com")

        # Deve generare WebSite e Organization
        categories = [f.file_name for f in fixes]
        assert "schema-website.jsonld" in categories
        assert "schema-organization.jsonld" in categories

        website_fix = [f for f in fixes if f.file_name == "schema-website.jsonld"][0]
        assert '"@type": "WebSite"' in website_fix.content
        assert "https://example.com" in website_fix.content

    def test_schema_completo_ritorna_vuoto(self):
        """If all schemas are present (WebSite + Organization + FAQPage), returns an empty list."""
        result = _make_result(
            **{
                "schema.has_website": True,
                "schema.has_faq": True,
                "schema.found_types": ["WebSite", "Organization", "FAQPage"],
            }
        )
        fixes = generate_schema_fix(result, "https://example.com")

        assert len(fixes) == 0

    def test_organization_schema_contiene_sameas(self):
        """The generated Organization template must include the sameAs field (#398)."""
        result = _make_result()
        fixes = generate_schema_fix(result, "https://example.com")

        org_fixes = [f for f in fixes if f.file_name == "schema-organization.jsonld"]
        assert len(org_fixes) == 1, "Deve essere generato lo schema Organization"

        import json

        schema = json.loads(org_fixes[0].content)
        assert "sameAs" in schema, "Il campo sameAs deve essere presente nello schema Organization"

    def test_organization_sameas_ha_almeno_due_url(self):
        """sameAs deve contenere almeno 2 URL placeholder (#398)."""
        result = _make_result()
        fixes = generate_schema_fix(result, "https://example.com")

        import json

        org_fix = next(f for f in fixes if f.file_name == "schema-organization.jsonld")
        schema = json.loads(org_fix.content)
        same_as = schema["sameAs"]

        assert isinstance(same_as, list), "sameAs deve essere una lista"
        assert len(same_as) >= 2, f"sameAs deve avere almeno 2 URL, trovati: {len(same_as)}"



    def test_faqpage_fix_has_single_canonical_url_fields(self):
        """FAQPage snippet includes url/@id and sitemap de-duplication guidance."""
        result = _make_result()
        fixes = generate_schema_fix(result, "https://example.com/")
        faq = next(f for f in fixes if f.file_name == "schema-faqpage.jsonld")
        import json

        data = json.loads(faq.content)
        assert data["url"] == "https://example.com"
        assert data["@id"] == "https://example.com#faq"
        assert "sitemap" in faq.description.lower()

    def test_organization_sameas_usa_domini_autorevoli(self):
        """I placeholder sameAs devono usare domini presenti in SAMEAS_AUTHORITATIVE_DOMAINS (#398)."""
        result = _make_result()
        fixes = generate_schema_fix(result, "https://example.com")

        import json
        from urllib.parse import urlparse

        org_fix = next(f for f in fixes if f.file_name == "schema-organization.jsonld")
        schema = json.loads(org_fix.content)
        same_as_urls = schema["sameAs"]

        authoritative_matches = 0
        for url in same_as_urls:
            parsed = urlparse(url)
            # Check se il netloc contiene almeno un domain autorevole
            for domain in SAMEAS_AUTHORITATIVE_DOMAINS:
                if domain in parsed.netloc:
                    authoritative_matches += 1
                    break

        assert authoritative_matches >= 2, (
            f"Almeno 2 URL sameAs devono usare domini autorevoli, trovati: {authoritative_matches}"
        )


# ============================================================================
# TEST: generate_meta_fix
# ============================================================================


class TestGenerateMetaFix:
    """Test per la generazione di fix meta tag."""

    def test_meta_mancanti_genera_tutti(self):
        """If all meta tags are missing, generates all of them."""
        result = _make_result()
        fix = generate_meta_fix(result, "https://example.com")

        assert fix is not None
        assert fix.category == "meta"
        assert "<title>" in fix.content
        assert 'name="description"' in fix.content
        assert 'rel="canonical"' in fix.content
        assert "og:title" in fix.content
        assert "og:description" in fix.content
        assert "og:image" in fix.content

    def test_meta_completo_ritorna_none(self):
        """Se tutti i meta tag sono presenti, non serve fix."""
        result = _make_optimized_result()
        fix = generate_meta_fix(result, "https://example.com")

        assert fix is None


class TestGenerateContentRewriteFix:
    """Test per i suggerimenti di rewrite del content."""

    def test_contenuto_debole_genera_piano_rewrite(self):
        """With weak content signals, generates a rewrite markdown."""
        result = _make_result(
            **{
                "content.has_h1": False,
                "content.word_count": 120,
                "content.has_links": False,
                "content.has_numbers": False,
                "content.has_heading_hierarchy": False,
                "content.has_front_loading": False,
            }
        )

        fix = generate_content_rewrite_fix(result, "https://example.com")

        assert fix is not None
        assert fix.category == "content"
        assert fix.file_name == "content-rewrite.md"
        assert "Priority Suggestions" in fix.content
        assert "opening 150 characters" in fix.content

    def test_contenuto_forte_non_genera_fix(self):
        """Se i segnali content sono solidi, non serve rewrite guidance."""
        result = _make_optimized_result()

        fix = generate_content_rewrite_fix(result, "https://example.com")

        assert fix is None


class TestGenerateVerticalFixTemplates:
    """Test per i template vertical-specific."""

    def test_vertical_templates_real_estate_bilingual(self):
        """Generates trust page + CTA + bilingual schema for real-estate in the en-fr locale."""
        result = _make_result(
            **{
                "vertical_profile": VerticalAuditResult(
                    checked=True,
                    vertical="real-estate-proptech",
                    market_locale="en-fr",
                )
            }
        )
        fixes = generate_vertical_fix_templates(result, "https://example.com")

        names = {f.file_name for f in fixes}
        assert "vertical/real-estate-proptech-trust-page.md" in names
        assert "vertical/real-estate-proptech-quote-cta.html" in names
        assert "vertical/schema-service-bilingual.jsonld" in names

    def test_vertical_templates_generic_none(self):
        """Does not generate a vertical template when the profile is generic/inactive."""
        result = _make_result(
            **{
                "vertical_profile": VerticalAuditResult(
                    checked=True,
                    vertical="generic",
                    market_locale="en",
                )
            }
        )
        fixes = generate_vertical_fix_templates(result, "https://example.com")
        assert fixes == []


class TestGenerateVerticalContentPack:
    """Test for opinionated per-vertical packs."""

    def test_property_management_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="real-estate-proptech",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/property-management-trust-legal-pack.md" in names

    def test_dental_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="healthcare-dental",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/dental-procedure-faq-scaffold.jsonld" in names
        assert "vertical/dental-procedure-explainer-template.md" in names

    def test_insurance_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="financial-services-insurance",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/insurance-comparison-block.html" in names
        assert "vertical/insurance-transparency-pack.md" in names

    def test_b2b_spec_sheet_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="manufacturing-industrial-b2b",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/b2b-spec-sheet-template.md" in names

    def test_travel_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="travel-hospitality",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/travel-intent-pack.md" in names
        assert "vertical/travel-itinerary-schema.jsonld" in names

    def test_ecommerce_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="ecommerce-retail",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/ecommerce-conversion-pack.md" in names
        assert "vertical/ecommerce-product-comparison-block.html" in names

    def test_saas_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="saas-technology",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/saas-demand-capture-pack.md" in names
        assert "vertical/saas-commercial-faq-schema.jsonld" in names

    def test_education_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="education-edtech-k12",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/education-lead-quality-pack.md" in names
        assert "vertical/education-curriculum-alignment-block.html" in names

    def test_home_services_pack_present(self):
        fixes = generate_vertical_content_pack(
            vertical="local-home-services",
            site_name="example.com",
            base_url="https://example.com",
        )
        names = {f.file_name for f in fixes}
        assert "vertical/local-home-services-trust-pack.md" in names
        assert "vertical/local-home-services-estimate-cta.html" in names


# ============================================================================
# TEST: run_all_fixes
# ============================================================================


class TestRunAllFixes:
    """Test per l'orchestratore run_all_fixes."""

    @patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None)
    @patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[])
    def test_genera_tutti_i_fix(self, mock_fetch, mock_discover):
        """With a completely unoptimised site, generates fixes for every category."""
        result = _make_result()
        plan = run_all_fixes("https://example.com", audit_result=result)

        assert plan.score_before == 30
        assert plan.score_estimated_after > plan.score_before
        assert len(plan.fixes) > 0

        categories = {f.category for f in plan.fixes}
        assert "robots" in categories
        assert "llms" in categories
        assert "schema" in categories
        assert "meta" in categories
        assert "content" in categories

    def test_sito_ottimizzato_no_fix(self):
        """With an already-optimised site, generates no fixes."""
        result = _make_optimized_result()
        plan = run_all_fixes("https://example.com", audit_result=result)

        assert len(plan.fixes) == 0
        assert len(plan.skipped) > 0

    @patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None)
    @patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[])
    def test_filtro_only(self, mock_fetch, mock_discover):
        """Il filtro --only limita le categorie."""
        result = _make_result()
        plan = run_all_fixes("https://example.com", audit_result=result, only={"robots"})

        categories = {f.category for f in plan.fixes}
        assert "robots" in categories
        assert "llms" not in categories
        assert "schema" not in categories
        assert "meta" not in categories
        assert "content" not in categories

    @patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None)
    @patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[])
    def test_filtro_only_vertical(self, mock_fetch, mock_discover):
        """The --only vertical filter generates only vertical artefacts."""
        result = _make_result(
            **{
                "vertical_profile": VerticalAuditResult(
                    checked=True,
                    vertical="local-home-services",
                    market_locale="en",
                )
            }
        )
        plan = run_all_fixes("https://example.com", audit_result=result, only={"vertical"})

        categories = {f.category for f in plan.fixes}
        assert categories == {"vertical"}
        assert any("local-home-services-trust-page.md" in f.file_name for f in plan.fixes)


# ============================================================================
# TEST: CLI geo fix
# ============================================================================


class TestFixCommand:
    """Test per il comando CLI geo fix."""

    @patch("geo_optimizer.cli.fix_cmd.validate_public_url", return_value=(True, None))
    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_fix_dry_run_mostra_preview(self, mock_audit, _mock_validate):
        """geo fix --url URL shows a preview without writing files."""
        mock_audit.return_value = _make_result()
        runner = CliRunner()

        with (
            patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None),
            patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[]),
        ):
            result = runner.invoke(cli, ["fix", "--url", "https://example.com"])

        assert result.exit_code == 0
        assert "PREVIEW" in result.output or "Fix plan" in result.output

    @patch("geo_optimizer.cli.fix_cmd.validate_public_url", return_value=(True, None))
    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_fix_apply_scrive_file(self, mock_audit, _mock_validate, tmp_path):
        """geo fix --url URL --apply scrive i file nella directory."""
        mock_audit.return_value = _make_result()
        runner = CliRunner()

        output_dir = str(tmp_path / "geo-fixes")
        with (
            patch("geo_optimizer.core.llms_generator.discover_sitemap", return_value=None),
            patch("geo_optimizer.core.llms_generator.fetch_sitemap", return_value=[]),
        ):
            result = runner.invoke(
                cli,
                [
                    "fix",
                    "--url",
                    "https://example.com",
                    "--apply",
                    "--output-dir",
                    output_dir,
                ],
            )

        assert result.exit_code == 0
        # Verifies that almeno un file sia status scritto
        from pathlib import Path

        output = Path(output_dir)
        assert output.exists()
        files = list(output.iterdir())
        assert len(files) > 0

    @patch("geo_optimizer.cli.fix_cmd.validate_public_url", return_value=(True, None))
    @patch("geo_optimizer.core.audit.run_full_audit")
    @patch("geo_optimizer.core.fixer.run_all_fixes")
    def test_fix_apply_rejects_unsafe_generated_file_name(self, mock_fixes, mock_audit, _mock_validate, tmp_path):
        """geo fix --apply refuses generated filenames that escape output-dir."""
        mock_audit.return_value = _make_result()
        mock_fixes.return_value = FixPlan(
            url="https://example.com",
            fixes=[
                FixItem(
                    category="robots",
                    description="Unsafe generated path",
                    content="User-agent: *\nAllow: /",
                    file_name="../outside.txt",
                    action="create",
                )
            ],
        )
        runner = CliRunner()

        outside = tmp_path / "outside.txt"
        result = runner.invoke(
            cli,
            [
                "fix",
                "--url",
                "https://example.com",
                "--apply",
                "--output-dir",
                str(tmp_path / "geo-fixes"),
            ],
        )

        assert result.exit_code != 0
        assert "Unsafe fix file path" in result.output
        assert not outside.exists()

    @patch("geo_optimizer.cli.fix_cmd.validate_public_url", return_value=(True, None))
    @patch("geo_optimizer.core.audit.run_full_audit")
    def test_fix_sito_ottimizzato(self, mock_audit, _mock_validate):
        """geo fix su sito già ottimizzato mostra messaggio positivo."""
        mock_audit.return_value = _make_optimized_result()
        runner = CliRunner()

        result = runner.invoke(cli, ["fix", "--url", "https://example.com"])

        assert result.exit_code == 0
        assert "No fixes needed" in result.output

    def test_fix_url_non_sicuro(self):
        """geo fix con URL locale is blocked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--url", "http://169.254.169.254/metadata"])

        assert result.exit_code != 0

    def test_fix_only_invalido(self):
        """geo fix --only invalido mostra errore."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--url", "https://example.com", "--only", "invalido"])

        assert result.exit_code != 0
        assert "Invalid categories" in result.output

    def test_fix_help(self):
        """geo fix --help works."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--help"])

        assert result.exit_code == 0
        assert "--url" in result.output
        assert "--apply" in result.output
        assert "--dry-run" in result.output
        assert "vertical" in result.output

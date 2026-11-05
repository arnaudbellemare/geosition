from bs4 import BeautifulSoup

from geo_optimizer.core.vertical_profile import audit_vertical_profile
from geo_optimizer.models.results import BrandEntityResult, ContentResult, MetaResult, SchemaResult


def test_vertical_profile_property_management_bilingual():
    html = """
    <html lang="en">
      <head>
        <link rel="alternate" hreflang="en-ca" href="https://example.com/en" />
        <link rel="alternate" hreflang="fr-ca" href="https://example.com/fr" />
      </head>
      <body>
        <h1>Property Management Montreal</h1>
        <a href="/services">Services</a>
        <a href="/contact">Contact Us</a>
        <p>Trusted by 120 landlords. Licensed and insured. Book a free consultation today.</p>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = audit_vertical_profile(
        soup=soup,
        base_url="https://example.com",
        schema=SchemaResult(has_organization=True, raw_schemas=[{"@type": "Organization"}]),
        meta=MetaResult(has_title=True),
        content=ContentResult(word_count=450),
        brand_entity=BrandEntityResult(has_contact_info=True, has_geo_schema=True, hreflang_count=2),
        vertical="real-estate-proptech",
        market_locale="en-fr",
    )
    assert result.checked is True
    assert result.vertical == "real-estate-proptech"
    assert result.bilingual_ready is True
    assert result.business_readiness_score > 0
    assert result.trust_signals >= 1
    assert result.conversion_signals >= 1


def test_vertical_profile_generic_missing_signals():
    soup = BeautifulSoup("<html><body><h1>Welcome</h1><p>Simple page.</p></body></html>", "html.parser")
    result = audit_vertical_profile(
        soup=soup,
        base_url="https://example.com",
        schema=SchemaResult(),
        meta=MetaResult(),
        content=ContentResult(word_count=40),
        brand_entity=BrandEntityResult(),
        vertical="generic",
        market_locale="en",
    )
    assert result.checked is True
    assert result.business_readiness_score >= 0
    assert len(result.priority_actions) >= 1


def test_vertical_profile_auto_detection_saas():
    html = """
    <html>
      <body>
        <h1>Acme Platform</h1>
        <p>Start free trial. Book demo. API integrations for teams.</p>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = audit_vertical_profile(
        soup=soup,
        base_url="https://acme.example.com/pricing",
        schema=SchemaResult(),
        meta=MetaResult(title_text="Acme SaaS Platform"),
        content=ContentResult(word_count=180),
        brand_entity=BrandEntityResult(),
        vertical="auto",
        market_locale="en",
    )
    assert result.detected_vertical == "saas-technology"
    assert result.vertical == "saas-technology"
    assert result.detection_confidence > 0.0

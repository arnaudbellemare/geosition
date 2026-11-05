"""Marketing audit orchestrator."""

from __future__ import annotations

from geo_optimizer.models.results import ImageAuditResult, MarketingResult, MediaResult, SerpResult

from .analysis import audit_ai_presence, audit_content_strategy, audit_copywriting, audit_images
from .planning import _build_marketing_actions, _compute_bonus


def audit_marketing(
    soup,
    base_url: str = "",
    schema=None,
    meta=None,
    content=None,
    conversion=None,
    citability=None,
    run_serp: bool = False,
    vertical: str = "auto",
    geo_result=None,
    rival_urls: list[str] | None = None,
    keyword: str | None = None,
) -> MarketingResult:
    """Run full marketing audit: copywriting + content strategy + AI presence + media + SERP.

    Args:
        soup: BeautifulSoup of the homepage.
        base_url: Page URL.
        schema: SchemaResult (checked for FAQ schema).
        meta: MetaResult (title tag analysis).
        content: ContentResult (word count context).
        conversion: ConversionResult (if already computed).
        citability: CitabilityResult (statistics density cross-ref).
        run_serp: Whether to run the SERP competitor analysis (makes ~10 HTTP requests).
        vertical: Site vertical hint for location page suggestions.
        geo_result: Full AuditResult (passed through to SERP extractor).
        rival_urls: Optional list of real Google competitor URLs to analyse directly
                    (skips automated SERP search when provided).
        keyword: Optional override keyword for SERP analysis.

    Returns:
        MarketingResult with scored sub-audits and prioritised actions.
    """
    if soup is None:
        return MarketingResult(checked=True)

    copy_result = audit_copywriting(soup, meta=meta, vertical=vertical, page_keyword=keyword or "")
    strategy_result = audit_content_strategy(soup, base_url=base_url, schema=schema, vertical=vertical)
    presence_result = audit_ai_presence(soup, base_url=base_url, schema=schema)

    # Image SEO audit (no network requests — pure HTML analysis)
    image_result: ImageAuditResult = audit_images(
        soup, base_url=base_url, page_keyword=keyword or "", vertical=vertical
    )

    # Media audit (lightweight — only HEAD requests for found assets)
    from geo_optimizer.core.audit_media import audit_media as _audit_media

    media_result: MediaResult = _audit_media(soup, base_url=base_url)

    # SERP competitor analysis (optional — network-heavy)
    serp_result: SerpResult = SerpResult()
    if run_serp or rival_urls:
        try:
            from geo_optimizer.core.audit_serp import audit_serp as _audit_serp

            serp_result = _audit_serp(
                soup,
                base_url=base_url,
                result=geo_result,
                vertical=vertical,
                rival_urls=rival_urls or None,
                keyword=keyword,
            )
        except (OSError, ValueError, AttributeError):
            serp_result = SerpResult(checked=False)

    # Build prioritised actions from all sub-audits + cross-refs
    actions = _build_marketing_actions(
        copy_result=copy_result,
        strategy_result=strategy_result,
        presence_result=presence_result,
        conversion=conversion,
        citability=citability,
        media_result=media_result,
    )

    # Composite: copywriting 30% + content strategy 30% + AI presence 20% + media 10% + bonus 10%
    bonus = _compute_bonus(conversion, citability)
    raw = (
        copy_result.copy_score * 0.30
        + strategy_result.content_score * 0.30
        + presence_result.presence_score * 0.20
        + media_result.media_score * 0.10
        + bonus * 0.10
    )
    marketing_score = min(100, round(raw))

    return MarketingResult(
        checked=True,
        marketing_score=marketing_score,
        copywriting=copy_result,
        content_strategy=strategy_result,
        ai_presence=presence_result,
        image_audit=image_result,
        media=media_result,
        serp=serp_result,
        priority_actions=actions,
    )

"""Marketing action planning helpers."""

from __future__ import annotations

from geo_optimizer.models.results import (
    AIPresenceResult,
    ContentStrategyResult,
    CopywritingResult,
    MarketingAction,
)


def _build_marketing_actions(
    copy_result: CopywritingResult,
    strategy_result: ContentStrategyResult,
    presence_result: AIPresenceResult | None = None,
    conversion=None,
    citability=None,
    media_result=None,
) -> list[MarketingAction]:
    """Build ranked marketing actions from sub-audit findings."""
    actions: list[MarketingAction] = []

    # Copy issues → actions
    if copy_result.h1_is_generic or not copy_result.h1_text:
        actions.append(
            MarketingAction(
                key="rewrite_h1",
                title="Rewrite H1 to be outcome-focused",
                why=f'Current H1 "{copy_result.h1_text[:40] or "(none)"}" is generic — '
                "visitors can't tell what you do in 5 seconds.",
                skill="copywriting",
                impact="high",
                effort="low",
                priority="P1",
                estimated_lift="+15-30% time-on-page",
            )
        )
    elif copy_result.h1_is_feature_focused and not copy_result.h1_is_outcome_focused:
        actions.append(
            MarketingAction(
                key="rewrite_h1_outcome",
                title="Reframe H1 from feature to customer outcome",
                why=f'H1 talks about what you do, not what the customer gets: "{copy_result.h1_text[:50]}"',
                skill="copywriting",
                impact="high",
                effort="low",
                priority="P1",
                estimated_lift="+10-20% engagement",
            )
        )

    if not copy_result.has_value_prop_in_hero:
        actions.append(
            MarketingAction(
                key="add_value_prop",
                title="Add value proposition sub-headline in hero",
                why="No clear 'you get X' framing above the fold — visitors must scroll to understand your offer.",
                skill="copywriting",
                impact="high",
                effort="low",
                priority="P1",
                estimated_lift="+20-40% scroll depth",
            )
        )

    if copy_result.weak_ctas and not copy_result.strong_ctas:
        actions.append(
            MarketingAction(
                key="upgrade_ctas",
                title=f'Upgrade CTAs from "{copy_result.weak_ctas[0]}" to action+outcome copy',
                why="Weak CTAs don't communicate value. 'Learn More' converts at ~1%; 'Start Free Trial' at ~3-8%.",
                skill="page-cro",
                impact="high",
                effort="low",
                priority="P1",
                estimated_lift="+50-200% CTA clicks",
            )
        )

    if copy_result.benefit_ratio < 0.3 and (copy_result.benefit_phrases + copy_result.feature_phrases) > 5:
        actions.append(
            MarketingAction(
                key="benefit_language",
                title="Rewrite copy from 'we-focused' to 'you-focused' language",
                why=f"Copy is {round((1 - copy_result.benefit_ratio) * 100)}% feature-focused. "
                "Customers buy outcomes, not features.",
                skill="copywriting",
                impact="medium",
                effort="medium",
                priority="P2",
                estimated_lift="+10-25% conversion rate",
            )
        )

    # Content strategy issues → actions
    if not strategy_result.has_comparison_pages:
        actions.append(
            MarketingAction(
                key="comparison_page",
                title="Create a '[Your brand] vs [Top competitor]' comparison page",
                why="Comparison content captures 33% of AI citations in competitive queries "
                "and drives high-intent visitors already evaluating options.",
                skill="competitor-alternatives",
                impact="high",
                effort="medium",
                priority="P2",
                estimated_lift="+30-50% organic AI citations",
            )
        )

    if not strategy_result.has_numbers_proof:
        actions.append(
            MarketingAction(
                key="numbers_proof",
                title="Add quantified social proof (customer count, results stats)",
                why="Specific numbers boost AI citation probability by +37% and lift conversion. "
                "'100+ properties managed' beats 'trusted by many clients'.",
                skill="copywriting",
                impact="high",
                effort="low",
                priority="P1",
                estimated_lift="+37% AI citation rate",
            )
        )

    if not strategy_result.has_faq_section:
        actions.append(
            MarketingAction(
                key="add_faq",
                title="Add FAQ section with FAQPage schema",
                why="FAQ blocks are directly extracted by Google AI Overviews and Perplexity. "
                "Each Q&A becomes a standalone citation target.",
                skill="schema-markup",
                impact="medium",
                effort="low",
                priority="P2",
                estimated_lift="+20-40% AI answer appearances",
            )
        )

    if not strategy_result.has_pricing_page:
        actions.append(
            MarketingAction(
                key="pricing_page",
                title="Create a /pricing or /plans page",
                why="Hidden pricing causes drop-off and prevents AI agents from recommending you "
                "when comparing products on behalf of users.",
                skill="pricing-strategy",
                impact="medium",
                effort="medium",
                priority="P2",
                estimated_lift="+15-25% qualified lead rate",
            )
        )

    if not strategy_result.has_blog:
        actions.append(
            MarketingAction(
                key="launch_blog",
                title="Launch content blog with 5 high-intent articles",
                why="Each blog article creates an independent AI citation surface. "
                "Without a blog, your entire AI visibility depends on the homepage alone.",
                skill="content-strategy",
                impact="high",
                effort="high",
                priority="P3",
                estimated_lift="+200-500% AI citation surface area",
            )
        )

    if not strategy_result.has_email_capture:
        actions.append(
            MarketingAction(
                key="email_capture",
                title="Add email capture / lead magnet",
                why="AI-referred visitors who aren't ready to book need a lower-commitment offer. "
                "A free guide or checklist captures them before they bounce.",
                skill="lead-magnets",
                impact="medium",
                effort="medium",
                priority="P3",
                estimated_lift="+10-20% lead capture rate",
            )
        )

    # AI presence issues → actions (ai-seo skill)
    if presence_result is not None:
        if presence_result.blocked_ai_bots:
            actions.append(
                MarketingAction(
                    key="unblock_ai_bots",
                    title=f"Unblock AI crawlers in robots.txt ({', '.join(presence_result.blocked_ai_bots[:3])})",
                    why="Blocked AI bots cannot index or cite your content on any AI platform. "
                    "This is a zero-traffic switch — every blocked bot = zero citations on that platform.",
                    skill="ai-seo",
                    impact="high",
                    effort="low",
                    priority="P1",
                    estimated_lift="+100% AI visibility (currently 0 for blocked bots)",
                )
            )

        if not presence_result.has_definition_block:
            actions.append(
                MarketingAction(
                    key="add_definition_block",
                    title="Add a definition sentence in the first 300 words",
                    why="AI systems extract '[Service] is [definition]' sentences for 'what is X' queries. "
                    "Without a definition block, you won't appear for definitional AI Overviews.",
                    skill="ai-seo",
                    impact="high",
                    effort="low",
                    priority="P1",
                    estimated_lift="+AI Overview citations for informational queries",
                )
            )

        if presence_result.unattributed_stat_count > 0 and not presence_result.has_attributed_stats:
            actions.append(
                MarketingAction(
                    key="attribute_statistics",
                    title=f"Add source attribution to {presence_result.unattributed_stat_count} statistic(s)",
                    why="Unattributed numbers are less citable — AI systems can't verify them. "
                    "'X% of customers' → 'According to [Source] (2024), X% of customers'.",
                    skill="ai-seo",
                    impact="medium",
                    effort="low",
                    priority="P1",
                    estimated_lift="+37% citation probability per attributed stat",
                )
            )

        if presence_result.js_heavy:
            actions.append(
                MarketingAction(
                    key="fix_js_rendering",
                    title="Server-render core content (page is JS-heavy, AI crawlers can't read it)",
                    why="AI crawlers (GPTBot, ClaudeBot, PerplexityBot) don't execute JavaScript. "
                    "Content only visible after JS runs is invisible to AI search engines.",
                    skill="ai-seo",
                    impact="high",
                    effort="high",
                    priority="P3",
                    estimated_lift="+AI indexability of all content",
                )
            )

        if not presence_result.has_location_pages:
            actions.append(
                MarketingAction(
                    key="location_pages",
                    title="Create location-specific service pages (/[service]-montreal/, etc.)",
                    why="The programmatic-seo Locations playbook: each service×city page captures "
                    "'[service] in [city]' searches and is an independent AI citation target.",
                    skill="programmatic-seo",
                    impact="medium",
                    effort="medium",
                    priority="P2",
                    estimated_lift="+local query coverage per city page",
                )
            )

        if not presence_result.has_org_sameas:
            actions.append(
                MarketingAction(
                    key="org_sameas",
                    title="Add sameAs links to Organization schema (LinkedIn, Google Business, Wikidata)",
                    why="sameAs links connect your entity across the web — AI systems use this for "
                    "entity recognition, making you more citable in brand and industry queries.",
                    skill="schema-markup",
                    impact="medium",
                    effort="low",
                    priority="P2",
                    estimated_lift="+entity authority for branded AI citations",
                )
            )

    # Media issues → actions
    if media_result is not None and media_result.checked:
        if media_result.large_videos:
            actions.append(
                MarketingAction(
                    key="compress_videos",
                    title=f"Compress {media_result.large_videos} video(s) for mobile (H.264 MP4, < 3 MB)",
                    why="Large video files cause slow load times on mobile. iOS/Android users bounce if video "
                    "takes > 3 s to start. Target H.264 MP4 at 720p/30fps, CRF 23.",
                    skill="media-optimization",
                    impact="high",
                    effort="medium",
                    priority="P1",
                    estimated_lift="-40-60% page load time for video-heavy pages",
                )
            )
        if media_result.missing_poster:
            actions.append(
                MarketingAction(
                    key="add_video_poster",
                    title=f"Add poster thumbnail to {media_result.missing_poster} video(s)",
                    why="Without poster=, mobile browsers show a blank black frame until video loads. "
                    "A good thumbnail increases play rate by 30%.",
                    skill="media-optimization",
                    impact="medium",
                    effort="low",
                    priority="P1",
                    estimated_lift="+30% video play rate",
                )
            )
        if media_result.autoplay_unmuted:
            actions.append(
                MarketingAction(
                    key="fix_autoplay",
                    title=f"Add muted attribute to {media_result.autoplay_unmuted} autoplay video(s)",
                    why="iOS and Android block unmuted autoplay — the video silently fails to play. "
                    "Add muted and playsinline attributes.",
                    skill="media-optimization",
                    impact="high",
                    effort="low",
                    priority="P1",
                    estimated_lift="Fixes broken video on all mobile browsers",
                )
            )
        if media_result.large_audios:
            actions.append(
                MarketingAction(
                    key="compress_audio",
                    title=f"Compress {media_result.large_audios} audio file(s) to MP3 128 kbps",
                    why="Audio files > 2 MB delay page load. Convert to MP3 128 kbps or Opus 96 kbps.",
                    skill="media-optimization",
                    impact="medium",
                    effort="low",
                    priority="P2",
                    estimated_lift="-60-80% audio file size",
                )
            )

    # Cross-ref: citability score low → add statistics
    if citability is not None:
        stat_score = getattr(citability, "statistics_score", None)
        if stat_score is not None and stat_score < 50:
            actions.append(
                MarketingAction(
                    key="add_statistics",
                    title="Add data and statistics with source citations",
                    why=f"Statistics score is {stat_score}/100. "
                    "Adding cited stats boosts AI visibility by +37% (Princeton GEO study).",
                    skill="ai-seo",
                    impact="high",
                    effort="medium",
                    priority="P2",
                    estimated_lift="+37% AI citation probability",
                )
            )

    # Sort: high impact first, then low effort first, then priority
    _impact_rank = {"high": 3, "medium": 2, "low": 1}
    _effort_rank = {"low": 3, "medium": 2, "high": 1}
    _priority_rank = {"P1": 3, "P2": 2, "P3": 1}
    actions.sort(
        key=lambda a: (
            _impact_rank.get(a.impact, 1),
            _effort_rank.get(a.effort, 1),
            _priority_rank.get(a.priority, 1),
        ),
        reverse=True,
    )

    return actions[:12]  # top 12 actions


def _compute_bonus(conversion=None, citability=None) -> int:
    """Compute bonus points from conversion + citability cross-reference."""
    score = 0
    if conversion is not None:
        score += min(50, getattr(conversion, "conversion_score", 0))
    if citability is not None:
        cit = getattr(citability, "score", 0)
        score += min(50, int(cit / 2))  # citability 0-100 → 0-50 bonus
    return min(100, score)


def _compute_copy_score(
    h1_is_generic: bool,
    h1_is_outcome: bool,
    has_value_prop: bool,
    weak_ctas: list,
    strong_ctas: list,
    benefit_ratio: float,
) -> int:
    score = 0
    # H1 quality (max 30)
    if h1_is_outcome:
        score += 30
    elif not h1_is_generic:
        score += 15

    # Value prop in hero (max 25)
    if has_value_prop:
        score += 25

    # CTA quality (max 25)
    if strong_ctas and not weak_ctas:
        score += 25
    elif strong_ctas:
        score += 15
    elif not weak_ctas:
        score += 10  # no CTAs at all is neutral

    # Benefit language (max 20)
    if benefit_ratio >= 0.5:
        score += 20
    elif benefit_ratio >= 0.3:
        score += 10
    elif benefit_ratio > 0:
        score += 5

    return min(100, score)


def _compute_strategy_score(
    has_blog: bool,
    has_faq_section: bool,
    has_comparison_pages: bool,
    has_pricing_page: bool,
    has_email_capture: bool,
    has_numbers_proof: bool,
    has_case_studies: bool,
) -> int:
    weights = {
        "blog": (has_blog, 20),
        "faq": (has_faq_section, 15),
        "comparison": (has_comparison_pages, 20),
        "pricing": (has_pricing_page, 15),
        "email": (has_email_capture, 10),
        "numbers": (has_numbers_proof, 15),
        "cases": (has_case_studies, 5),
    }
    return sum(w for detected, w in weights.values() if detected)

"""
HTML formatter for standalone GEO audit reports.

Generates a self-contained HTML file with embedded CSS, openable
directly in the browser. Used with ``geo audit --format html``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from geo_optimizer.cli.scoring_helpers import (
    brand_entity_score as _brand_entity_score,
)
from geo_optimizer.cli.scoring_helpers import (
    content_score as _content_score,
)
from geo_optimizer.cli.scoring_helpers import (
    llms_score as _llms_score,
)
from geo_optimizer.cli.scoring_helpers import (
    meta_score as _meta_score,
)
from geo_optimizer.cli.scoring_helpers import (
    robots_score as _robots_score,
)
from geo_optimizer.cli.scoring_helpers import (
    schema_score as _schema_score,
)
from geo_optimizer.cli.scoring_helpers import (
    signals_score as _signals_score,
)
from geo_optimizer.core.scoring import CATEGORY_MAX_SCORES
from geo_optimizer.models.results import AuditResult


def format_audit_html(result: AuditResult) -> str:
    """Generate standalone HTML report with embedded CSS."""
    band_colors = {
        "excellent": "#22c55e",
        "good": "#06b6d4",
        "foundation": "#eab308",
        "critical": "#ef4444",
    }
    band_labels = {
        "excellent": "EXCELLENT",
        "good": "GOOD",
        "foundation": "FOUNDATION",
        "critical": "CRITICAL",
    }
    color = band_colors.get(result.band, "#888")
    band_label = band_labels.get(result.band, result.band.upper())

    # Build check table rows (fix #325, #341: max dinamici + 3 categorie mancanti)
    checks = [
        ("Robots.txt", _robots_score(result), CATEGORY_MAX_SCORES["robots"], result.robots.citation_bots_ok),
        ("llms.txt", _llms_score(result), CATEGORY_MAX_SCORES["llms"], result.llms.found and result.llms.has_h1),
        ("Schema JSON-LD", _schema_score(result), CATEGORY_MAX_SCORES["schema"], result.schema.has_website),
        (
            "Meta Tags",
            _meta_score(result),
            CATEGORY_MAX_SCORES["meta"],
            result.meta.has_title and result.meta.has_description,
        ),
        ("Content Quality", _content_score(result), CATEGORY_MAX_SCORES["content"], result.content.has_h1),
        (
            "Signals",
            _signals_score(result),
            CATEGORY_MAX_SCORES["signals"],
            bool(result.signals and result.signals.has_lang),
        ),
        (
            "AI Discovery",
            result.score_breakdown.get("ai_discovery", 0),
            CATEGORY_MAX_SCORES["ai_discovery"],
            bool(result.ai_discovery and result.ai_discovery.has_well_known_ai),
        ),
        (
            "Brand & Entity",
            _brand_entity_score(result),
            CATEGORY_MAX_SCORES["brand_entity"],
            bool(result.brand_entity and result.brand_entity.brand_name_consistent),
        ),
    ]

    check_rows = ""
    for name, score, max_score, passed in checks:
        icon = "✅" if passed else "❌"
        pct = int(score / max_score * 100) if max_score > 0 else 0
        check_rows += f"""
        <tr>
            <td>{name}</td>
            <td>{score}/{max_score}</td>
            <td>
                <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>
            </td>
            <td class="status">{icon}</td>
        </tr>"""

    agent_actions = _build_agent_actions(result, checks)
    agent_plan = _build_agent_plan(result, agent_actions)
    agent_plan_json = _json_for_html(agent_plan)
    agent_prompt = _build_agent_prompt(agent_plan)
    agent_actions_html = _format_agent_actions_html(agent_actions)

    # Recommendations
    recs_html = ""
    if result.recommendations:
        recs_items = "".join(
            f"<li>{_escape(rec)} <small>[{('provider guidance' if i < len(result.recommendation_evidence) and result.recommendation_evidence[i].get('level') == 'provider_guidance' else 'product heuristic')}]</small></li>"
            for i, rec in enumerate(result.recommendations)
        )
        recs_html = f"""
        <div class="section">
            <h2>Recommendations</h2>
            <ol>{recs_items}</ol>
        </div>"""

    # Found schemas
    schemas_html = ""
    if result.schema.found_types:
        tags = " ".join(f'<span class="tag">{_escape(t)}</span>' for t in result.schema.found_types)
        schemas_html = f'<div class="schemas">Found schemas: {tags}</div>'

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEO Audit — {_escape(result.url)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f172a;color:#e2e8f0;padding:2rem;max-width:800px;margin:0 auto}}
h1{{font-size:1.5rem;margin-bottom:.5rem}}
h2{{font-size:1.1rem;margin-bottom:.75rem;color:#94a3b8}}
h3{{font-size:.95rem;margin:.25rem 0 .45rem;color:#e2e8f0}}
.header{{text-align:center;margin-bottom:2rem}}
.url{{color:#94a3b8;font-size:.9rem;word-break:break-all}}
.score-ring{{display:inline-flex;align-items:center;justify-content:center;
width:140px;height:140px;border-radius:50%;border:6px solid {color};
margin:1.5rem 0;font-size:2.5rem;font-weight:700;color:{color}}}
.band{{font-size:1.1rem;font-weight:600;color:{color};margin-bottom:1rem}}
.section{{background:#1e293b;border-radius:8px;padding:1.25rem;margin-bottom:1rem}}
.section.lead{{border:1px solid #334155}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:.5rem .75rem;text-align:left}}
th{{color:#94a3b8;font-weight:500;font-size:.85rem;border-bottom:1px solid #334155}}
td{{border-bottom:1px solid #1e293b}}
.bar-bg{{background:#334155;border-radius:4px;height:8px;width:100px}}
.bar-fill{{background:{color};border-radius:4px;height:8px;transition:width .3s}}
.status{{text-align:center}}
.tag{{display:inline-block;background:#334155;padding:.15rem .5rem;border-radius:4px;
font-size:.8rem;margin:.15rem}}
.schemas{{margin-top:.75rem}}
ol{{padding-left:1.5rem}}
li{{margin-bottom:.4rem;line-height:1.5}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.65rem;margin-top:.85rem}}
.summary-card{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:.75rem}}
.summary-card strong{{display:block;color:#f8fafc;font-size:1.15rem}}
.summary-card span{{display:block;color:#94a3b8;font-size:.78rem;margin-top:.15rem}}
.action-card{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:1rem;margin:.75rem 0}}
.action-top{{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.5rem}}
.pill{{display:inline-flex;align-items:center;border-radius:999px;padding:.15rem .5rem;font-size:.72rem;font-weight:700}}
.p1{{background:#7f1d1d;color:#fecaca}}.p2{{background:#713f12;color:#fde68a}}.p3{{background:#1e3a8a;color:#bfdbfe}}
.category{{background:#334155;color:#cbd5e1}}
.action-card p{{color:#cbd5e1;line-height:1.5;margin:.35rem 0}}
.action-card ul{{padding-left:1.1rem;margin:.4rem 0;color:#cbd5e1}}
.agent-block{{background:#020617;border:1px solid #334155;border-radius:8px;padding:1rem;overflow:auto;white-space:pre-wrap;color:#dbeafe;font-size:.82rem;line-height:1.45}}
.machine-note{{color:#94a3b8;font-size:.82rem;line-height:1.45;margin-bottom:.75rem}}
.footer{{text-align:center;margin-top:2rem;color:#64748b;font-size:.8rem}}
.footer a{{color:#60a5fa}}
</style>
<script type="application/json" id="geo-agent-plan">{agent_plan_json}</script>
</head>
<body>
<div class="header">
    <h1>GEO Audit Report</h1>
    <div class="url">{_escape(result.url)}</div>
    <div class="score-ring">{result.score}</div>
    <div class="band">{band_label}</div>
</div>

<div class="section lead">
    <h2>AI Implementation Plan</h2>
    <p class="machine-note">
        This section is built for an AI coding agent. It converts the audit into executable tasks,
        likely files to inspect, and acceptance checks. The same plan is embedded as JSON in
        <code>#geo-agent-plan</code>.
    </p>
    <div class="summary-grid">
        <div class="summary-card"><strong>{len(agent_actions)}</strong><span>agent tasks</span></div>
        <div class="summary-card"><strong>{sum(1 for a in agent_actions if a["priority"] == "P1")}</strong><span>P1 blockers</span></div>
        <div class="summary-card"><strong>{sum(1 for a in agent_actions if a["priority"] == "P2")}</strong><span>P2 improvements</span></div>
        <div class="summary-card"><strong>{result.score}/100</strong><span>current GEO score</span></div>
    </div>
    {agent_actions_html}
</div>

<div class="section">
    <h2>Copy/Paste Agent Prompt</h2>
    <p class="machine-note">Paste this into a coding agent with access to the website repository.</p>
    <pre class="agent-block">{_escape(agent_prompt)}</pre>
</div>

<div class="section">
    <h2>Check Results</h2>
    <table>
        <thead>
            <tr><th>Check</th><th>Score</th><th>Progress</th><th>Status</th></tr>
        </thead>
        <tbody>{check_rows}
        </tbody>
    </table>
    {schemas_html}
</div>

{recs_html}

<div class="footer">
    Generated on {timestamp} by
    <a href="https://github.com/arnaudbellemare/geosition">GEOSITION</a>
</div>
</body>
</html>"""


def _escape(text: str) -> str:
    """Escape special HTML characters (fix #20: usa html.escape standard)."""
    import html as _html

    return _html.escape(text, quote=True)


def _build_agent_actions(result: AuditResult, checks: list[tuple[str, int, int, bool]]) -> list[dict]:
    """Build an implementation-oriented action list for AI agents."""
    actions: list[dict] = []

    for index, action in enumerate(result.next_actions, start=1):
        title = action.title.strip() or f"Address {action.key or 'GEO readiness gap'}"
        category = _classify_action(title, action.key)
        actions.append(
            {
                "id": f"next-{index}",
                "priority": action.priority or _priority_for_index(index),
                "category": category,
                "title": title,
                "why": action.why.strip() or "This item is part of the generated GEO execution roadmap.",
                "source": "next_actions",
                "expected_score_gain": action.expected_score_gain,
                "files_to_inspect": _files_for_category(category),
                "acceptance_checks": _acceptance_checks_for_category(category),
                "agent_instruction": _agent_instruction(title, category),
            }
        )

    for index, recommendation in enumerate(result.recommendations, start=1):
        category = _classify_action(recommendation, "")
        actions.append(
            {
                "id": f"rec-{index}",
                "priority": _priority_for_index(index),
                "category": category,
                "title": recommendation,
                "why": "Direct audit recommendation.",
                "source": "recommendations",
                "expected_score_gain": 0,
                "files_to_inspect": _files_for_category(category),
                "acceptance_checks": _acceptance_checks_for_category(category),
                "agent_instruction": _agent_instruction(recommendation, category),
            }
        )

    if not actions:
        for index, (name, score, max_score, passed) in enumerate(checks, start=1):
            if passed:
                continue
            category = _classify_action(name, "")
            actions.append(
                {
                    "id": f"check-{index}",
                    "priority": "P2",
                    "category": category,
                    "title": f"Improve {name} from {score}/{max_score}",
                    "why": f"The {name} check did not pass in this audit.",
                    "source": "failed_checks",
                    "expected_score_gain": max(max_score - score, 0),
                    "files_to_inspect": _files_for_category(category),
                    "acceptance_checks": _acceptance_checks_for_category(category),
                    "agent_instruction": _agent_instruction(f"Improve {name}", category),
                }
            )

    if not actions:
        actions.append(
            {
                "id": "monitor-1",
                "priority": "P3",
                "category": "monitoring",
                "title": "Keep monitoring GEO readiness after future content changes",
                "why": "The current audit did not return blocking recommendations.",
                "source": "generated",
                "expected_score_gain": 0,
                "files_to_inspect": ["content pages", "templates/layout", "robots.txt", "llms.txt"],
                "acceptance_checks": ["Run geo audit again and confirm the score remains stable or improves."],
                "agent_instruction": "Re-run the audit after the next content or template change and compare the score.",
            }
        )

    return actions


def _build_agent_plan(result: AuditResult, actions: list[dict]) -> dict:
    return {
        "schema_version": "geo-agent-plan-v1",
        "site_url": result.url,
        "score": result.score,
        "band": result.band,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_order": ["P1", "P2", "P3"],
        "commands": [
            f"geo audit {result.url}",
            f"geo fix {result.url} --output ./geo-fixes",
        ],
        "actions": actions,
    }


def _build_agent_prompt(plan: dict) -> str:
    lines = [
        "You are improving this website for AI search/citation readiness.",
        f"Site: {plan['site_url']}",
        f"Current GEO score: {plan['score']}/100 ({plan['band']})",
        "",
        "Work through every task below in priority order. For each task:",
        "1. Inspect the listed files or nearest equivalent in the repository.",
        "2. Implement the smallest safe change that satisfies the acceptance checks.",
        "3. Do not remove existing analytics, security headers, canonical tags, or business-critical copy.",
        "4. Re-run the relevant checks, then summarize changed files and remaining risks.",
        "",
        "Tasks:",
    ]
    for action in plan["actions"]:
        files = ", ".join(action["files_to_inspect"])
        checks = "; ".join(action["acceptance_checks"])
        lines.extend(
            [
                f"- [{action['priority']}] {action['title']}",
                f"  Category: {action['category']}",
                f"  Inspect: {files}",
                f"  Acceptance: {checks}",
                f"  Instruction: {action['agent_instruction']}",
            ]
        )
    return "\n".join(lines)


def _format_agent_actions_html(actions: list[dict]) -> str:
    cards = []
    for action in actions:
        files = "".join(f"<li>{_escape(item)}</li>" for item in action["files_to_inspect"])
        checks = "".join(f"<li>{_escape(item)}</li>" for item in action["acceptance_checks"])
        priority_class = action["priority"].lower()
        cards.append(
            f"""
            <div class="action-card">
                <div class="action-top">
                    <span class="pill {priority_class}">{_escape(action["priority"])}</span>
                    <span class="pill category">{_escape(action["category"])}</span>
                </div>
                <h3>{_escape(action["title"])}</h3>
                <p><strong>Why:</strong> {_escape(action["why"])}</p>
                <p><strong>Agent instruction:</strong> {_escape(action["agent_instruction"])}</p>
                <p><strong>Files to inspect:</strong></p>
                <ul>{files}</ul>
                <p><strong>Acceptance checks:</strong></p>
                <ul>{checks}</ul>
            </div>"""
        )
    return "".join(cards)


def _json_for_html(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2).replace("<", "\\u003c")


def _priority_for_index(index: int) -> str:
    if index <= 2:
        return "P1"
    if index <= 6:
        return "P2"
    return "P3"


def _classify_action(text: str, key: str) -> str:
    value = f"{key} {text}".lower()
    if "robots" in value or "bot" in value:
        return "robots"
    if "llms" in value:
        return "llms"
    if "schema" in value or "json-ld" in value or "faqpage" in value or "website" in value:
        return "schema"
    if "meta" in value or "title" in value or "description" in value or "canonical" in value:
        return "meta"
    if "content" in value or "copy" in value or "h1" in value or "faq" in value:
        return "content"
    if "ai discovery" in value or "/ai/" in value or ".well-known" in value:
        return "ai_discovery"
    if "brand" in value or "entity" in value or "organization" in value:
        return "brand_entity"
    if "lang" in value or "rss" in value or "signal" in value:
        return "signals"
    return "general"


def _files_for_category(category: str) -> list[str]:
    mapping = {
        "robots": ["robots.txt", "server/static asset routing", "deployment public folder"],
        "llms": ["llms.txt", "docs or content index", "deployment public folder"],
        "schema": ["base layout <head>", "JSON-LD/schema components", "homepage/content templates"],
        "meta": ["base layout <head>", "SEO metadata component", "page title/description source"],
        "content": ["homepage content", "service/product pages", "FAQ or help content"],
        "ai_discovery": ["/.well-known/ai.txt", "/ai/summary.json", "/ai/faq.json", "static/public routes"],
        "brand_entity": ["homepage", "about page", "organization schema", "contact page"],
        "signals": ["HTML root/layout", "sitemap/RSS generation", "content freshness metadata"],
        "monitoring": ["audit workflow", "CI job", "report artifacts"],
        "general": ["homepage", "shared layout", "content templates"],
    }
    return mapping.get(category, mapping["general"])


def _acceptance_checks_for_category(category: str) -> list[str]:
    mapping = {
        "robots": ["Citation bots are allowed in robots.txt.", "geo audit no longer reports robots blockers."],
        "llms": ["llms.txt exists with a clear H1 and key links.", "The file is reachable from the site root."],
        "schema": ["Valid JSON-LD is present on the relevant page.", "Schema matches visible page content."],
        "meta": [
            "Every target page has title, description, canonical, and OG tags.",
            "No duplicate or empty metadata.",
        ],
        "content": [
            "Content includes a clear H1, concrete facts, FAQs, and useful citations.",
            "Important copy renders in raw HTML.",
        ],
        "ai_discovery": ["AI discovery files exist and return 200.", "Files link to canonical high-value pages."],
        "brand_entity": ["Brand/entity naming is consistent.", "Organization details match schema and visible copy."],
        "signals": [
            "HTML language/freshness/feed signals are present where relevant.",
            "No conflicting indexability signals.",
        ],
        "monitoring": [
            "A follow-up audit can compare score and recommendations.",
            "Report artifacts are stored with timestamp.",
        ],
        "general": [
            "The recommendation is implemented with a minimal, reviewable diff.",
            "A follow-up audit confirms improvement.",
        ],
    }
    return mapping.get(category, mapping["general"])


def _agent_instruction(title: str, category: str) -> str:
    return (
        f"Implement this {category} fix: {title}. Preserve existing behavior, validate generated markup, "
        "and update or add tests/docs when the repository has a matching pattern."
    )


# Functions _robots_score, _llms_score, _schema_score, _meta_score, _content_score
# are imported from scoring_helpers (fix #77 — removed duplication)

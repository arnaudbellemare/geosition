<div align="center">

<img src="assets/logo.svg" alt="GEOSITION" width="480"/>

# GEOSITION

### Make your website visible to AI search engines

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![CI](https://github.com/arnaudbellemare/geosition/actions/workflows/ci.yml/badge.svg)](https://github.com/arnaudbellemare/geosition/actions)
[![License: Source available](https://img.shields.io/badge/license-source--available-22c55e?style=flat-square)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-8b5cf6?style=flat-square)](https://modelcontextprotocol.io)
**Audit · Score · Fix · Monitor — for AI citation readiness.**

[Quick Start](#quick-start) · [Changelog](CHANGELOG.md)

</div>

---

## Why this exists

AI search engines like Perplexity, ChatGPT, and Google AI give direct answers and **cite their sources**. If your site isn't optimized for these engines, you're invisible — even if you rank #1 on Google.

```
User asks: "What's the best property management company in Montreal?"

Perplexity: "According to [Competitor.com], their services include..."
             ↑ They appear. You don't.
```

GEOSITION audits your website for AI search readiness using technical and content checks informed by provider guidance and research, and generates suggested fixes. The readiness score does not measure citations or guarantee visibility. See [Google guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide), [OpenAI publisher guidance](https://help.openai.com/en/articles/12627856-publishers-and-developers-faq), and the [Princeton GEO paper](https://arxiv.org/abs/2311.09735).

---

## Quick Start

```bash
pip install geosition
```

Then run your first audit:

```bash
geo audit --url https://yoursite.com
```

You'll get a score out of 100 and a prioritized list of what to fix.

---

## Common Commands

### One-shot: audit and fix everything

```bash
geo autopilot --url https://yoursite.com --repo . --apply
```

This audits your site, generates fixes, applies them to your repo, then re-runs the audit and shows the improvement.

### Step by step (recommended for first run)

```bash
# 1. Audit — see your score and what's missing
geo audit --url https://yoursite.com

# 2. Preview fixes before applying
geo fix --url https://yoursite.com

# 3. Apply fixes to your local repo
geo fix --url https://yoursite.com --apply

# 4. Save a baseline so you can track changes over time
geo audit --url https://yoursite.com --save-history
```

### Make your site callable as an AI agent tool

```bash
geo agent --url https://yoursite.com
geo agent --url https://yoursite.com --apply
```

Generates the full endpoint stack so AI agents (Claude, ChatGPT, Perplexity) can use your site as a tool — not just cite it, but actually call it:

| File | What it does |
|------|-------------|
| `.well-known/ai.txt` | Agent declaration — tells agents who you are |
| `ai/summary.json` | Machine-readable site identity |
| `ai/faq.json` | Answers agents can surface directly in responses |
| `ai/service.json` | Service capabilities for agent tool selection |
| `ai/tools.json` | WebMCP tool definitions — makes your site callable |

Also generates `potentialAction` JSON-LD and `registerTool()` / `toolname` HTML snippets for browser agents. Future-proofs for the agent era.

---

### Competitor comparison

```bash
geo rivalry --url https://yoursite.com --output rivalry-report.md
```

### Large sites (sitemap mode)

```bash
geo audit --sitemap https://yoursite.com/sitemap.xml --max-urls 25
```

### Weekly monitoring

```bash
geo audit --url https://yoursite.com --save-history --regression
geo monitor --domain yoursite.com
geo track --url https://yoursite.com --report --output ai-readiness-report.html
```

### Other useful commands

```bash
# Compare before/after versions of a page
geo diff --before https://yoursite.com/old --after https://yoursite.com/new

# Generate llms.txt (the AI equivalent of robots.txt)
geo llms --base-url https://yoursite.com --output ./public/llms.txt

# Generate JSON-LD schema markup
geo schema --type faq --url https://yoursite.com

# Content audit (keyword density, E-E-A-T, entity signals)
geo content --url https://yoursite.com --keywords "property management,montreal"

# Audit a GitHub repo's SEO/AI visibility health
geo github --repo-path .

# Internal link graph and orphan page detection
geo links --sitemap https://yoursite.com/sitemap.xml

# Cross-page terminology consistency
geo coherence --sitemap https://yoursite.com/sitemap.xml

# AI crawler log analysis
geo logs --file access.log

# Saved AI answer archive and citation quality
geo snapshots --query "best AI visibility tool"
geo snapshots --quality --snapshot-id 12 --target-domain yoursite.com
```

You can also use these shorter aliases for the same commands:

```bash
aiv visibility-audit --url https://yoursite.com
aiv scanner --url https://yoursite.com
aiv scorer --url https://yoursite.com
aiv fixer --url https://yoursite.com --apply
```

---

## What it checks

| Area | Points | What GEOSITION looks for |
|------|--------|------------------------------|
| **Robots.txt** | /25 | Search crawler access; training crawler access is a separate choice. |
| **Schema JSON-LD** | /16 | Structured data and entity details where applicable. |
| **Meta Tags** | /20 | Titles, descriptions, canonical URLs and social metadata. |
| **Content** | /21 | Headings, links, structure and other content heuristics. |
| **Brand & Entity** | /10 | Business identity and contact signals. |
| **Signals** | /8 | Language, feed and freshness signals. |
| **llms.txt and AI discovery files** | Unscored | Optional informational checks; not required for Google Search. |

**Score bands:** 86–100 Excellent · 68–85 Good · 36–67 Foundation · 0–35 Critical

The dashboard supports read-only Google Search Console and Bing Webmaster connections for verified domains, with daily synchronization when OAuth, durable storage, and the scheduler are configured. These are search traffic totals, not AI-only citation counts. See [first-party search measurements](docs/search-measurement.md) for setup and limitations.

**Bonus checks** (informational, don't affect your score):

| Check | What it detects |
|-------|-----------------|
| **CDN Crawler Access** | Does Cloudflare/Akamai/Vercel block GPTBot, ClaudeBot, PerplexityBot? |
| **JS Rendering** | Is content accessible without JavaScript? SPA framework detection |
| **WebMCP Readiness** | Chrome WebMCP support: `registerTool()`, `toolname` attributes, `potentialAction` schema |
| **Negative Signals** | 8 anti-citation signals: CTA overload, popups, thin content, keyword stuffing, missing author, boilerplate ratio |
| **Prompt Injection Detection** | 8 manipulation patterns: hidden text, invisible Unicode, LLM instructions, HTML comment injection, monochrome text, micro-font, data-attr injection, aria-hidden abuse |
| **Trust Stack Score** | 5-layer trust aggregation (Technical, Identity, Social, Academic, Consistency) — composite grade A–F |
| **RAG Chunk Readiness** | Content segmentation for RAG retrieval: section word counts, definition openings, heading boundaries, anchor sentences |
| **Content Decay Prediction** | Detects temporal, statistical, version, event, and price decay patterns — evergreen score 0–100 |
| **Platform Citation Profile** | Per-platform readiness scores for ChatGPT, Perplexity, Google AI |

A separate **Citability Score** summarizes content heuristics. It is not a measurement of citations, and individual checks do not guarantee an uplift. Use repeated visibility tests and first-party analytics to measure outcomes.

---

## Vertical Mode

Running with `--vertical auto` detects your business type automatically and adapts recommendations for it. Supported verticals:

- `ecommerce-retail`
- `travel-hospitality`
- `healthcare-dental`
- `real-estate-proptech`
- `legal-professional-services`
- `manufacturing-industrial-b2b`
- `financial-services-insurance`
- `saas-technology`
- `education-edtech-k12`
- `local-home-services`

This adds a **Business Readiness Score** (trust, conversion path, locality clarity, vertical relevance) with prioritized actions for your industry.

Use `--only vertical` to generate vertical-specific content directly — trust page templates, conversion CTA blocks, bilingual service schema, FAQ scaffolds, and more:

```bash
geo fix --url https://yoursite.com --vertical auto --market-locale en-fr --only vertical --apply
```

---

## Output Formats

```bash
geo audit --url https://example.com                    # Human-readable (default)
geo audit --url https://example.com --format json      # Machine-readable
geo audit --url https://example.com --format rich      # Colored terminal output
geo audit --url https://example.com --format html      # Self-contained HTML report
geo audit --url https://example.com --format sarif     # GitHub Code Scanning
geo audit --url https://example.com --format junit     # Jenkins / GitLab CI
geo audit --url https://example.com --format github    # GitHub Actions annotations
```

---

## CI/CD Integration

```yaml
# .github/workflows/geo.yml
- uses: arnaudbellemare/geosition@v1
  with:
    url: https://yoursite.com
    min-score: 70        # Fail the build if score drops below 70
    format: sarif        # Upload results to GitHub Security tab
```

Works with GitHub Actions, GitLab CI, Jenkins, CircleCI, and any CI that runs Python.

To catch regressions over time:

```bash
geo audit --url https://yoursite.com --save-history --regression
```

---

## MCP Server

Use GEOSITION directly from Claude, Cursor, Windsurf, or any MCP client:

```bash
pip install geosition[mcp]
claude mcp add geosition -- geo-mcp
```

Then just ask: *"audit my site and fix what's missing"*

| Tool | What it does |
|------|-------------|
| `geo_audit` | Full audit with score and recommendations |
| `geo_fix` | Generate fix files |
| `geo_llms_generate` | Generate llms.txt |
| `geo_citability` | Content citability analysis (47 methods) |
| `geo_schema_validate` | Validate JSON-LD |
| `geo_compare` | Compare multiple sites side by side |
| `geo_gap_analysis` | Explain the gap between two sites and prioritize fixes |
| `geo_ai_discovery` | Check AI discovery endpoints |
| `geo_check_bots` | Check bot access via robots.txt |
| `geo_trust_score` | 5-layer trust signal aggregation |
| `geo_negative_signals` | 8 anti-citation signal detection |
| `geo_factual_accuracy` | Audit unsourced claims, contradictions, and broken citations |

---

## Use as AI Context

Load the right file into your AI assistant to get GEOSITION expertise:

| Platform | File |
|----------|------|
| Claude Projects | [`ai-context/claude-project.md`](ai-context/claude-project.md) |
| ChatGPT Custom GPT | [`ai-context/chatgpt-custom-gpt.md`](ai-context/chatgpt-custom-gpt.md) |
| Cursor | [`ai-context/cursor.mdc`](ai-context/cursor.mdc) |
| Windsurf | [`ai-context/windsurf.md`](ai-context/windsurf.md) |
| Kiro | [`ai-context/kiro-steering.md`](ai-context/kiro-steering.md) |

---

## Python API

```python
from geo_optimizer import audit

result = audit("https://example.com")
print(result.score)                  # 85
print(result.band)                   # "good"
print(result.citability.total_score) # 72
print(result.score_breakdown)        # {"robots": 18, "llms": 14, ...}
print(result.recommendations)        # ["Add FAQPage schema..."]
```

Async variant:

```python
from geo_optimizer import audit_async
result = await audit_async("https://example.com")
```

---

## Dynamic Badge

Show your GEOSITION score in your README:

```markdown
![GEOSITION Score](https://geosition-web.onrender.com/badge?url=https://yoursite.com)
```

Colors: 86–100 green · 68–85 cyan · 36–67 yellow · 0–35 red. Cached 1h.

---

## Plugin System

Extend the audit with custom checks:

```toml
[project.entry-points."geo_optimizer.checks"]
my_check = "mypackage:MyCheck"
```

See [`examples/example_plugin.py`](examples/example_plugin.py) for a working example.

---

## Research Foundation

| Paper | Venue | Key Finding |
|-------|-------|-------------|
| [GEO: Generative Engine Optimization](https://arxiv.org/abs/2311.09735) | **KDD 2024** | 9 methods tested on 10k queries. Cite Sources +115%, Statistics +40% |
| [AutoGEO](https://arxiv.org/abs/2510.11438) | **ICLR 2026** | Automatic rule extraction. +50.99% over Princeton baseline |
| [C-SEO Bench](https://arxiv.org/abs/2506.11097) | **2025** | Most content manipulation is ineffective. Infrastructure matters most |

The research is clear: if crawlers can't find and parse your content, prose optimization doesn't help. GEOSITION focuses on **technical infrastructure** (robots.txt, llms.txt, schema, meta) first.

---

## Roadmap

| Version | Window | Codename |
|---------|--------|----------|
| v4.10.0 | Late May / Early Jun 2026 | Veil |
| v4.11.0 | Mid / Late Jul 2026 | Static |
| v4.12.0 | Sep 2026 | Ledger |
| v4.13.0 | Nov 2026 | Quiet Glass |
| v4.14.0-rc1 | Jan 2027 | Threshold |
| v5.0.0 | May 2027 | Black Archive |

Full calendar → [docs/ROADMAP.md](docs/ROADMAP.md)

---

## Security

All URL inputs are validated against private IP ranges (RFC 1918, loopback, link-local, cloud metadata) with DNS pinning before any request is made. See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

---

## Contributing

```bash
git clone https://github.com/arnaudbellemare/geosition.git
cd geosition && pip install -e ".[dev]"   # or: pip install geosition
pytest tests/ -v   # 1393 tests
```

[Bug reports](https://github.com/arnaudbellemare/geosition/issues/new) · [Feature requests](https://github.com/arnaudbellemare/geosition/issues/new) · [CONTRIBUTING.md](CONTRIBUTING.md)

---

<div align="center">

**Source-available license (MIT with rider)** · Built by [Arnaud Bellemare](https://github.com/arnaudbellemare)

If this saved you time, a star helps others find it.

[![Star on GitHub](https://img.shields.io/github/stars/arnaudbellemare/geosition?style=for-the-badge&color=facc15&logo=github&label=Star)](https://github.com/arnaudbellemare/geosition/stargazers)

</div>

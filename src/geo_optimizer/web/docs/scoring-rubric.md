# AI search readiness scoring

The 0–100 readiness score is a heuristic based on signals GEOSITION can inspect. It is **not** a measurement of citations, rankings, traffic, or conversions, and does not predict them. Scores under this model are not directly comparable with older scores.

| Category | Maximum | What it checks |
| --- | ---: | --- |
| Crawler access | 25 | robots.txt and search crawler access; wildcard permissions count. |
| Structured data | 16 | JSON-LD presence and selected types and properties. |
| Metadata | 20 | Titles, descriptions, canonical and social metadata. |
| Content | 21 | Structure, links and other content heuristics. |
| Technical signals | 8 | Language, feed and freshness signals. |
| Brand and entity | 10 | Identity, contact and selected entity signals. |
| llms.txt and AI discovery files | 0 | Optional informational checks; no effect on the score. |

The weights are product heuristics, not measured effects or provider ranking weights. A signal's presence is not proof of quality. Some checks, such as preferred title lengths, minimum word counts, and social metadata, are heuristics rather than universal AI search requirements. The separate citability score is also heuristic.

Search visibility and model training are separate crawler choices. Check provider guidance before changing robots.txt. An explicit search bot rule is not inherently better than an effective wildcard rule. A missing robots.txt file should be reviewed in context; its absence does not itself mean crawling is blocked.

For measured results, compare first-party Search Console and Bing Webmaster Tools reports, referral traffic and conversions, and repeated AI answer tests. Provider reports and sampled tests cover different surfaces and should not be treated as interchangeable.

## Evidence

- **Provider guidance:** [Google AI features](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide), [OpenAI publisher guidance](https://help.openai.com/en/articles/12627856-publishers-and-developers-faq), [Anthropic crawlers](https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler), and [Bing AI Performance](https://blogs.bing.com/webmaster/2026/2/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview/).
- **Research:** [GEO (KDD 2024)](https://arxiv.org/abs/2311.09735) and [AutoGEO (ICLR 2026)](https://arxiv.org/abs/2510.11438) report results under specific experimental conditions. Those results do not establish a universal improvement for each check.
- **Product heuristics:** GEOSITION's weights and checks are engineering choices and should not be represented as provider ranking signals or guaranteed gains.

Google states that llms.txt does not affect Google Search visibility and is not required for its AI features. Other services may choose to use it.

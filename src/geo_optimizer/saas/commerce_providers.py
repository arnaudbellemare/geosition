"""Documented provider-specific paths for guided commerce preparation.

These are guidance, not evidence of a connection, provider approval, or eligibility.
"""

from __future__ import annotations

PROVIDERS = [
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "updated": "2026-11-13",
        "summary": "Prepare your public site for search; a private connector and a merchant feed are separate options.",
        "steps": [
            {
                "id": "chatgpt_search",
                "title": "Review ChatGPT search access",
                "kind": ["products", "services", "both"],
                "detail": "Review OAI-SearchBot access and the public pages customers need. Search access does not establish indexing or a ranking. Training access is a separate choice.",
                "url": "https://developers.openai.com/api/docs/bots",
                "link": "OpenAI crawler guidance",
            },
            {
                "id": "chatgpt_feed",
                "title": "Prepare a product feed",
                "kind": ["products", "both"],
                "detail": "Map authorized products, prices, availability, and images. Feed onboarding requires partner approval; a draft feed does not mean submission or acceptance.",
                "url": "https://developers.openai.com/commerce/guides/get-started",
                "link": "OpenAI product feed guidance",
            },
            {
                "id": "chatgpt_connector",
                "title": "Consider a private ChatGPT connector",
                "kind": ["products", "services", "both"],
                "detail": "If a private tool is useful, an owner can review a custom MCP connection and its access. A private connector is not a public merchant listing or an approved checkout.",
                "url": "https://developers.openai.com/plugins/deploy/connect-chatgpt",
                "link": "ChatGPT connection guidance",
            },
        ],
    },
    {
        "id": "claude",
        "name": "Claude",
        "updated": "2026-11-13",
        "summary": "Review access to your public site; a custom connector is a separate private tool connection.",
        "steps": [
            {
                "id": "claude_search",
                "title": "Review Claude search access",
                "kind": ["products", "services", "both"],
                "detail": "Review Claude-SearchBot and Claude-User access for the pages you want available. Training crawler preferences are separate; access does not prove inclusion in answers.",
                "url": "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
                "link": "Anthropic crawler guidance",
            },
            {
                "id": "claude_connector",
                "title": "Consider a private Claude connector",
                "kind": ["products", "services", "both"],
                "detail": "If a private tool is useful, review a custom remote MCP connector with the owner. Claude connects to the remote server from Anthropic's cloud; the OpenAI tunnel is not that endpoint. A connector is not a public listing.",
                "url": "https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp",
                "link": "Claude connector guidance",
            },
        ],
    },
]

PROVIDER_STEP_IDS = frozenset(step["id"] for provider in PROVIDERS for step in provider["steps"])

"""
Agent endpoint generator.

Generates WebMCP / tool-calling ready endpoints so AI agents can use a
website as a tool. Covers:
  - /.well-known/ai.txt        agent declaration
  - /ai/summary.json           machine-readable site identity
  - /ai/faq.json               Q&A for agents
  - /ai/service.json           service capabilities
  - /ai/tools.json             WebMCP tool definitions
  - potentialAction JSON-LD    schema.org action embedding snippet
  - WebMCP HTML snippet        registerTool() / toolname attribute guide

All functions return dataclasses, NEVER print.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from geo_optimizer.core.audit_ai_discovery import audit_ai_discovery
from geo_optimizer.utils.http import fetch_url

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class AgentFile:
    path: str  # e.g. "ai/tools.json"
    content: str  # file content to write
    description: str  # human-readable summary of what this file does


@dataclass
class AgentReadinessResult:
    url: str
    site_name: str
    site_description: str

    # What already exists
    has_well_known_ai: bool = False
    has_summary: bool = False
    has_faq: bool = False
    has_service: bool = False
    has_tools: bool = False

    # Whether the site exposes callable agent/LLM/API services
    offers_agent_services: bool = False

    # Files to generate
    files: list[AgentFile] = field(default_factory=list)

    # Snippets (not written to disk, shown to developer)
    snippets: list[AgentFile] = field(default_factory=list)

    @property
    def endpoints_present(self) -> int:
        return sum(
            [
                self.has_well_known_ai,
                self.has_summary,
                self.has_faq,
                self.has_service,
                self.has_tools,
            ]
        )

    @property
    def agent_ready(self) -> bool:
        return self.endpoints_present >= 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_site_name(base_url: str, html: str | None) -> str:
    if html:
        m = re.search(r"<title[^>]*>([^<]{2,80})</title>", html, re.IGNORECASE)
        if m:
            return re.sub(r"\s*[|\-–—].*$", "", m.group(1)).strip()
    return urlparse(base_url).hostname or "My Site"


def _extract_description(html: str | None) -> str:
    if html:
        m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']{10,300})["\']', html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "AI-powered website optimized for agent access."


def _check_tools_endpoint(base_url: str) -> bool:
    from urllib.parse import urljoin

    r, err = fetch_url(urljoin(base_url, "/ai/tools.json"))
    return bool(r and not err and r.status_code == 200)


# Strong signals: any one of these alone indicates the site exposes agent/API/LLM services
_AGENT_SERVICE_SIGNALS = re.compile(
    r"""
    \b(
        api | sdk | webhook | chatbot | llm | gpt | openai | anthropic |
        graphql | grpc | mcp | webmcp |
        ai[-\s]agent | agent[-\s]api | ai[-\s]platform | ai[-\s]service | ai[-\s]tool |
        rest[-\s]api | function[-\s]calling | tool[-\s]calling |
        developer[-\s]portal | developer[-\s]docs | api[-\s]docs
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Interactive signals: credentials/sandbox language strongly implies callable service
_INTERACTIVE_SIGNALS = re.compile(
    r"""
    \b(
        api[-\s]?key | bearer[-\s]?token | oauth | playground |
        rate[-\s]?limit | endpoint[-\s]?url | curl | swagger | openapi
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# URL path signals (not word-boundary based)
_PATH_SIGNALS = re.compile(r'href=["\'][^"\']*/(api|docs|swagger|openapi|graphql)[/"\'?]', re.IGNORECASE)


def _site_offers_agent_services(html: str | None, tools_json: str | None) -> bool:
    """Return True if the site appears to expose callable agent/LLM/API functionality.

    Checks:
    - tools.json has real callable tools (POST endpoints or parameterised tools)
    - Homepage HTML contains API/agent/LLM service signals
    """
    # tools.json with POST endpoints or parameterised tools is the strongest signal
    if tools_json:
        try:
            data = json.loads(tools_json)
            for tool in data.get("tools", []):
                method = str(tool.get("method", "GET")).upper()
                params = tool.get("parameters", {})
                if method == "POST" or (isinstance(params, dict) and len(params) > 0):
                    return True
        except (json.JSONDecodeError, ValueError):
            pass

    if not html:
        return False

    # Strip script/style blocks to avoid false positives from minified JS
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)

    return (
        bool(_AGENT_SERVICE_SIGNALS.search(clean))
        or bool(_INTERACTIVE_SIGNALS.search(clean))
        or bool(_PATH_SIGNALS.search(clean))
    )


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------


def _gen_well_known_ai(name: str, description: str, base_url: str) -> str:
    hostname = urlparse(base_url).hostname or base_url
    return f"""# AI Agent Declaration — {hostname}
# Generated by GEOSITION (https://github.com/arnaudbellemare/geosition)

name: {name}
description: {description}
api-base: {base_url}/ai
tools: {base_url}/ai/tools.json
summary: {base_url}/ai/summary.json
faq: {base_url}/ai/faq.json
service: {base_url}/ai/service.json
contact: {base_url}/contact
"""


def _gen_summary(name: str, description: str, base_url: str) -> str:
    return json.dumps(
        {
            "name": name,
            "description": description,
            "url": base_url,
            "capabilities": [
                "answer questions about services",
                "provide contact information",
                "explain pricing and process",
            ],
            "agent_endpoints": {
                "tools": f"{base_url}/ai/tools.json",
                "faq": f"{base_url}/ai/faq.json",
                "service": f"{base_url}/ai/service.json",
            },
            "schema_version": "1.0",
        },
        indent=2,
    )


def _gen_faq(name: str, base_url: str) -> str:
    faqs = [
        {
            "question": f"What does {name} do?",
            "answer": f"{name} provides services accessible at {base_url}. Contact us for details about our offerings.",
        },
        {
            "question": "How can I get in touch?",
            "answer": f"Visit {base_url}/contact or reach out through our website.",
        },
        {
            "question": "What areas or markets do you serve?",
            "answer": "Please visit our website for up-to-date information on our service area.",
        },
        {
            "question": "How do I get started?",
            "answer": f"Visit {base_url} and use the contact form or phone number to get started.",
        },
    ]
    return json.dumps({"faqs": faqs}, indent=2)


def _gen_service(name: str, description: str, base_url: str) -> str:
    return json.dumps(
        {
            "name": name,
            "description": description,
            "url": base_url,
            "serviceType": "General",
            "capabilities": [
                "information lookup",
                "contact facilitation",
                "service explanation",
            ],
            "endpoints": {
                "tools": f"{base_url}/ai/tools.json",
                "summary": f"{base_url}/ai/summary.json",
                "faq": f"{base_url}/ai/faq.json",
            },
        },
        indent=2,
    )


def _gen_tools(name: str, base_url: str) -> str:
    tools = [
        {
            "name": "get_site_summary",
            "description": f"Get a summary of {name} including what they do and how to contact them.",
            "parameters": {},
            "endpoint": f"{base_url}/ai/summary.json",
            "method": "GET",
        },
        {
            "name": "get_faqs",
            "description": f"Get frequently asked questions and answers about {name}.",
            "parameters": {},
            "endpoint": f"{base_url}/ai/faq.json",
            "method": "GET",
        },
        {
            "name": "get_services",
            "description": f"Get the list of services and capabilities offered by {name}.",
            "parameters": {},
            "endpoint": f"{base_url}/ai/service.json",
            "method": "GET",
        },
    ]
    return json.dumps({"tools": tools, "schema_version": "1.0"}, indent=2)


def _gen_potential_action_snippet(name: str, base_url: str) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": name,
        "url": base_url,
        "potentialAction": [
            {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": f"{base_url}/search?q={{search_term_string}}",
                },
                "query-input": "required name=search_term_string",
            },
            {
                "@type": "ViewAction",
                "name": "Get AI Summary",
                "target": f"{base_url}/ai/summary.json",
            },
            {
                "@type": "ViewAction",
                "name": "Get Agent Tools",
                "target": f"{base_url}/ai/tools.json",
            },
        ],
    }
    json_str = json.dumps(schema, indent=2)
    return f'<script type="application/ld+json">\n{json_str}\n</script>'


def _gen_webmcp_snippet(name: str, base_url: str) -> str:
    return f"""<!-- WebMCP Agent Integration — add to your <head> or main layout -->

<!-- 1. Declare your tool manifest -->
<link rel="ai-tools" href="{base_url}/ai/tools.json" />

<!-- 2. Mark interactive elements with toolname so agents can act on them -->
<button toolname="contact_form" aria-label="Contact {name}">Contact Us</button>
<input toolname="search_query" type="search" placeholder="Search..." />

<!-- 3. Register tools programmatically (if using WebMCP-compatible browser) -->
<script>
if (window.registerTool) {{
  window.registerTool({{
    name: 'get_site_summary',
    description: 'Get information about {name}',
    async execute() {{
      const res = await fetch('{base_url}/ai/summary.json');
      return res.json();
    }}
  }});

  window.registerTool({{
    name: 'get_faqs',
    description: 'Get FAQs about {name}',
    async execute() {{
      const res = await fetch('{base_url}/ai/faq.json');
      return res.json();
    }}
  }});
}}
</script>"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_agent_endpoint_generator(url: str) -> AgentReadinessResult:
    """Audit agent readiness and generate all missing endpoint files.

    Args:
        url: Public URL of the site.

    Returns:
        AgentReadinessResult with current status and files to generate.
    """
    # Fetch homepage to extract name/description
    r, _ = fetch_url(url)
    html = r.text if r else None

    name = _extract_site_name(url, html)
    description = _extract_description(html)
    base_url = url.rstrip("/")

    # Check existing endpoints
    discovery = audit_ai_discovery(base_url)
    has_tools = _check_tools_endpoint(base_url)

    # Fetch tools.json content for richer signal detection
    from urllib.parse import urljoin

    tools_r, _ = fetch_url(urljoin(base_url, "/ai/tools.json"))
    tools_json = tools_r.text if tools_r and tools_r.status_code == 200 else None

    offers_agent_services = _site_offers_agent_services(html, tools_json)

    result = AgentReadinessResult(
        url=base_url,
        site_name=name,
        site_description=description,
        has_well_known_ai=discovery.has_well_known_ai,
        has_summary=discovery.has_summary,
        has_faq=discovery.has_faq,
        has_service=discovery.has_service,
        has_tools=has_tools,
        offers_agent_services=offers_agent_services,
    )

    # Generate missing files
    if not discovery.has_well_known_ai:
        result.files.append(
            AgentFile(
                path=".well-known/ai.txt",
                content=_gen_well_known_ai(name, description, base_url),
                description="Agent declaration file — tells crawlers and agents who you are",
            )
        )

    if not discovery.has_summary:
        result.files.append(
            AgentFile(
                path="ai/summary.json",
                content=_gen_summary(name, description, base_url),
                description="Machine-readable site identity for AI agents",
            )
        )

    if not discovery.has_faq:
        result.files.append(
            AgentFile(
                path="ai/faq.json",
                content=_gen_faq(name, base_url),
                description="FAQ answers agents can surface directly in responses",
            )
        )

    if not discovery.has_service:
        result.files.append(
            AgentFile(
                path="ai/service.json",
                content=_gen_service(name, description, base_url),
                description="Service capabilities declaration for agent tool selection",
            )
        )

    if not has_tools:
        result.files.append(
            AgentFile(
                path="ai/tools.json",
                content=_gen_tools(name, base_url),
                description="WebMCP tool definitions — makes your site callable as an AI tool",
            )
        )

    # potentialAction JSON-LD — always useful for discoverability
    result.snippets.append(
        AgentFile(
            path="potentialAction JSON-LD snippet",
            content=_gen_potential_action_snippet(name, base_url),
            description="Add to your <head> — schema.org actions for agent discoverability",
        )
    )

    # WebMCP HTML snippet — only if the site actually exposes callable services
    if offers_agent_services:
        result.snippets.append(
            AgentFile(
                path="WebMCP HTML snippet",
                content=_gen_webmcp_snippet(name, base_url),
                description="Add to your layout — registerTool() + toolname attributes for browser agents",
            )
        )

    return result

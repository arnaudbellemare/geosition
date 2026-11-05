"""
Answer Engine Optimization (AEO) audit.

AEO covers three distinct citation-capture surfaces that differ from
standard GEO/SEO work:

1. Featured Snippet readiness — structure that wins paragraph, list,
   and table snippets in AI-generated overviews.
2. People Also Ask (PAA) optimization — Q&A structure that feeds PAA
   boxes and AI follow-up questions.
3. Knowledge Panel eligibility — entity signals that help search engines
   build a Knowledge Graph entry for the site/brand.

All checks are static (soup-based) — no SERP API calls required.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import AEOResult

# Question words that commonly appear in PAA / featured snippet queries
_QUESTION_STARTS = re.compile(
    r"^\s*(what|who|why|when|where|how|can|is|are|does|do|will|should|which|was|were)\b",
    re.IGNORECASE,
)
_ANSWER_TARGET_MIN = 40  # words — too short = not useful
_ANSWER_TARGET_MAX = 60  # words — too long = won't be picked as paragraph snippet
_LIST_SNIPPET_MIN = 3  # minimum list items for list-snippet eligibility


def _schema_objects(schema_result) -> list[dict]:
    """Return schema dicts from the real SchemaResult and legacy test doubles."""
    schemas = getattr(schema_result, "raw_schemas", None)
    if schemas is None:
        schemas = getattr(schema_result, "schemas_found", [])

    pending = list(schemas or [])
    objects: list[dict] = []
    while pending:
        item = pending.pop(0)
        if not isinstance(item, dict):
            continue
        objects.append(item)
        graph = item.get("@graph")
        if isinstance(graph, list):
            pending.extend(graph)
    return objects


def _schema_types(schema: dict) -> set[str]:
    raw_type = schema.get("@type", "")
    if isinstance(raw_type, list):
        return {str(item) for item in raw_type}
    return {str(raw_type)} if raw_type else set()


def audit_aeo(soup, schema_result=None, brand_entity_result=None) -> AEOResult:
    """Run AEO audit against a parsed HTML page.

    Args:
        soup: BeautifulSoup of the page.
        schema_result: Optional SchemaResult — used for FAQ/KG signals.
        brand_entity_result: Optional BrandEntityResult — used for KP signals.

    Returns:
        AEOResult with three sub-scores and a recommendations list.
    """
    result = AEOResult(checked=True)
    _audit_featured_snippet(soup, result)
    _audit_paa(soup, schema_result, result)
    _audit_knowledge_panel(soup, schema_result, brand_entity_result, result)
    _build_recommendations(result)
    return result


# ─── Featured Snippet ─────────────────────────────────────────────────────────


def _audit_featured_snippet(soup, result: AEOResult) -> None:
    """Check for paragraph, list, and table snippet eligibility."""
    body = soup.find("body")
    if not body:
        return

    # Paragraph snippet: first body paragraph ≤ _ANSWER_TARGET_MAX words that
    # starts with a subject + verb (direct-answer structure)
    paragraphs = body.find_all("p")
    for p in paragraphs[:10]:
        text = p.get_text(separator=" ", strip=True)
        words = text.split()
        if _ANSWER_TARGET_MIN <= len(words) <= _ANSWER_TARGET_MAX:
            result.has_paragraph_snippet_candidate = True
            result.snippet_candidate_word_count = len(words)
            break

    # List snippet: ordered or unordered list with ≥ _LIST_SNIPPET_MIN items
    for lst in body.find_all(["ul", "ol"]):
        items = lst.find_all("li", recursive=False)
        if len(items) >= _LIST_SNIPPET_MIN:
            result.has_list_snippet_candidate = True
            result.list_snippet_item_count = len(items)
            break

    # Table snippet: any <table> with ≥ 2 rows and ≥ 2 columns
    for table in body.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) >= 2:
            first_row_cells = rows[0].find_all(["th", "td"])
            if len(first_row_cells) >= 2:
                result.has_table_snippet_candidate = True
                break

    result.featured_snippet_score = sum(
        [
            result.has_paragraph_snippet_candidate,
            result.has_list_snippet_candidate,
            result.has_table_snippet_candidate,
        ]
    )


# ─── People Also Ask ─────────────────────────────────────────────────────────


def _audit_paa(soup, schema_result, result: AEOResult) -> None:
    """Check PAA readiness: Q&A headings, FAQ schema, answer conciseness."""
    body = soup.find("body")
    if not body:
        return

    # Q&A headings: H2/H3 that look like questions
    question_headings = 0
    for tag in body.find_all(["h2", "h3"]):
        text = tag.get_text(strip=True)
        if _QUESTION_STARTS.match(text) or text.rstrip().endswith("?"):
            question_headings += 1

    result.question_heading_count = question_headings
    result.has_question_headings = question_headings >= 2

    # FAQ schema Q&A pairs
    if schema_result is not None:
        faq_count = getattr(schema_result, "faq_item_count", 0)
        if faq_count == 0:
            for s in _schema_objects(schema_result):
                if "FAQPage" in _schema_types(s):
                    faq_count = len(s.get("mainEntity", []))
                    break
        result.faq_schema_item_count = faq_count
        result.has_faq_schema = faq_count >= 2

    # Coverage: question types present (what/how/why/when/can/is)
    all_heading_text = " ".join(t.get_text(strip=True) for t in body.find_all(["h2", "h3"])).lower()
    covered = {
        w for w in ["what", "how", "why", "when", "can", "is", "are"] if re.search(rf"\b{w}\b", all_heading_text)
    }
    result.paa_question_types_covered = sorted(covered)

    result.paa_score = sum(
        [
            result.has_question_headings,
            result.has_faq_schema,
            bool(len(covered) >= 2),
        ]
    )


# ─── Knowledge Panel ─────────────────────────────────────────────────────────


def _audit_knowledge_panel(soup, schema_result, brand_entity_result, result: AEOResult) -> None:
    """Check Knowledge Panel / Knowledge Graph eligibility signals."""
    # sameAs with authoritative sources
    authoritative_domains = {"wikidata.org", "wikipedia.org", "dbpedia.org", "freebase.com"}
    same_as_links: list[str] = []

    if schema_result is not None:
        for s in _schema_objects(schema_result):
            sa = s.get("sameAs", [])
            if isinstance(sa, str):
                sa = [sa]
            same_as_links.extend(str(link) for link in sa)

    authoritative_count = sum(1 for link in same_as_links if any(d in link for d in authoritative_domains))
    result.kg_same_as_count = len(same_as_links)
    result.kg_authoritative_same_as = authoritative_count
    result.has_wikidata_link = any("wikidata.org" in link for link in same_as_links)
    result.has_wikipedia_link = any("wikipedia.org" in link for link in same_as_links)

    # NAP consistency: Organization schema with name + telephone + address
    has_org_schema = False
    has_nap = False
    if schema_result is not None:
        for s in _schema_objects(schema_result):
            if "Organization" in _schema_types(s):
                has_org_schema = True
                has_nap = bool(s.get("name") and s.get("telephone") and s.get("address"))
                break

    result.has_org_schema = has_org_schema
    result.has_nap_consistency = has_nap

    # Founder / person entity
    if schema_result is not None:
        for s in _schema_objects(schema_result):
            if s.get("founder"):
                result.has_founder_entity = True
                break

    result.knowledge_panel_score = sum(
        [
            result.has_wikidata_link or result.has_wikipedia_link,
            result.has_nap_consistency,
            bool(authoritative_count >= 1),
            result.has_founder_entity,
        ]
    )


# ─── Recommendations ─────────────────────────────────────────────────────────


def _build_recommendations(result: AEOResult) -> None:
    if not result.has_paragraph_snippet_candidate:
        result.recommendations.append(
            "Featured snippet: add a direct 40–60-word answer paragraph near the top of the page "
            "— AI overviews prefer pages that answer the query in the opening."
        )
    if not result.has_list_snippet_candidate:
        result.recommendations.append(
            "List snippet: structure at least one key concept as a <ul>/<ol> with 3+ items "
            "— list snippets are among the most cited formats in AI answers."
        )
    if not result.has_question_headings:
        result.recommendations.append(
            "PAA: add at least 2 question-format H2/H3 headings (starting with What/How/Why/Can…) "
            "to match People Also Ask surfaces and AI follow-up queries."
        )
    if not result.has_faq_schema:
        result.recommendations.append(
            "PAA: add FAQPage JSON-LD schema with ≥ 2 Q&A pairs to qualify for PAA boxes and "
            "AI-generated answer attribution."
        )
    if not result.has_wikidata_link and not result.has_wikipedia_link:
        result.recommendations.append(
            "Knowledge Panel: add a Wikidata or Wikipedia URL to the Organization sameAs array "
            "to support Knowledge Graph entity recognition."
        )
    if not result.has_nap_consistency:
        result.recommendations.append(
            "Knowledge Panel: ensure Organization schema has consistent name, telephone, and address "
            "(NAP) — required for local Knowledge Panel eligibility."
        )

"""Citability: entity-oriented detection functions.

Covers: entity disambiguation, entity resolution, knowledge graph density,
retrieval triggers, E-E-A-T signals.
"""

from __future__ import annotations

import json
import re

from geo_optimizer.core.citability._helpers import _get_clean_text
from geo_optimizer.models.results import MethodScore

# ─── Shared regex for entity/KG/retrieval ────────────────────────────────────

# Regex: explicit relationship verbs for knowledge graph density
_KG_RELATION_RE = re.compile(
    r"\b(?:"
    r"is\s+a|is\s+the|is\s+an|are\s+the|was\s+founded|founded\s+(?:in|by)"
    r"|belongs?\s+to|part\s+of|consists?\s+of|includes?"
    r"|developed\s+by|created\s+by|built\s+by|maintained\s+by|owned\s+by"
    r"|located\s+in|based\s+in|headquartered\s+in"
    r"|acquired\s+by|merged\s+with|partnered\s+with"
    r"|invented\s+by|designed\s+by|authored\s+by"
    r"|known\s+as|also\s+called|referred\s+to\s+as|formerly"
    r"|type\s+of|kind\s+of|category\s+of|subset\s+of"
    r"|è\s+un[ao]?|sono\s+i|fa\s+parte\s+di|si\s+trova\s+[ai]"
    r"|fondato\s+(?:da|nel)|creato\s+da|sviluppato\s+da"
    r")\b",
    re.IGNORECASE,
)

# Regex: retrieval trigger phrases that help RAG systems select content
_RETRIEVAL_TRIGGER_RE = re.compile(
    r"\b(?:"
    r"according\s+to|research\s+shows|studies?\s+(?:show|found|indicate|suggest)"
    r"|data\s+(?:shows?|indicates?|suggests?|reveals?)"
    r"|evidence\s+(?:shows?|suggests?|indicates?)"
    r"|experts?\s+(?:say|recommend|suggest|agree|note)"
    r"|(?:the\s+)?official\s+(?:documentation|guide|specification)"
    r"|(?:as\s+of|since|starting|beginning)\s+\d{4}"
    r"|(?:defined|specified|described)\s+(?:as|in|by)"
    r"|in\s+(?:summary|conclusion|practice|short|brief)"
    r"|the\s+(?:key|main|primary|most\s+important)\s+(?:difference|benefit|advantage|factor)"
    r"|(?:step|phase|stage)\s+\d"
    r"|(?:compared?\s+to|versus|vs\.?|unlike|in\s+contrast)"
    r"|(?:for\s+example|for\s+instance|such\s+as|e\.g\.|i\.e\.)"
    r"|(?:best\s+practice|recommended\s+approach|industry\s+standard)"
    r"|(?:FAQ|frequently\s+asked)"
    r"|(?:how\s+to|what\s+is|why\s+(?:does|is|do)|when\s+to)"
    r")\b",
    re.IGNORECASE,
)


# ─── Entity Disambiguation (+8%) — Batch A v3.16.0 ───────────────────────────


def detect_entity_disambiguation(soup) -> MethodScore:
    """Detect entity disambiguation signals: consistent naming and explicit definitions."""
    score = 0

    # 1. Collect names from title, og:title, schema name
    names: list[str] = []
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        # Take the part before common separators
        raw = title_tag.string.strip()
        parts = re.split(r"\s*[|\-–—]\s*", raw)
        if parts:
            names.append(parts[0].strip().lower())

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        parts = re.split(r"\s*[|\-–—]\s*", og_title["content"])
        if parts:
            names.append(parts[0].strip().lower())

    # Name from JSON-LD schema
    schema_name = None
    sameas_count = 0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    if "name" in item and not schema_name:
                        schema_name = str(item["name"]).strip().lower()
                        names.append(schema_name)
                    same_as = item.get("sameAs", [])
                    if isinstance(same_as, str):
                        same_as = [same_as]
                    if isinstance(same_as, list):
                        sameas_count = max(sameas_count, len(same_as))
        except (json.JSONDecodeError, TypeError):
            continue

    # Check consistency: at least 2 names and all matching
    if len(names) >= 2:
        unique_names = set(names)
        if len(unique_names) == 1:
            score += 1

    # 2. First sentence contains an explicit definition of the brand/site
    body = soup.find("body")
    if body:
        # Find the first meaningful paragraph
        first_p = body.find("p")
        if first_p:
            first_text = first_p.get_text(strip=True)
            # Look for definition pattern: "X is...", "X è..."
            if re.search(r"\b(?:is|are|è|sono)\s+(?:a|an|the|un|una|il|la|lo)\b", first_text, re.I):
                score += 1

    # 3. sameAs with > 3 links (disambiguation bonus)
    if sameas_count > 3:
        score += 1

    return MethodScore(
        name="entity_disambiguation",
        label="Entity Disambiguation",
        detected=score >= 2,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "names_found": names,
            "names_consistent": len(set(names)) <= 1 if names else False,
            "sameas_count": sameas_count,
        },
    )


# ─── 22. E-E-A-T Composite (+15%) — Quality Signal Batch 2 ──────────────────


def detect_eeat(soup) -> MethodScore:
    """Detect E-E-A-T trust signals not covered by detect_authoritative_tone."""
    score = 0

    # Trust signals: privacy policy, terms, about, contact
    trust_links = {"privacy": False, "terms": False, "about": False, "contact": False}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        link_text = a.get_text(strip=True).lower()
        combined = href + " " + link_text
        if "privacy" in combined or "cookie" in combined:
            trust_links["privacy"] = True
        if "terms" in combined or "tos" in combined or "condizioni" in combined:
            trust_links["terms"] = True
        if "about" in combined or "chi-siamo" in combined or "chi siamo" in combined:
            trust_links["about"] = True
        if "contact" in combined or "contatti" in combined:
            trust_links["contact"] = True

    trust_count = sum(trust_links.values())
    score += min(trust_count, 3)

    # Experience: author with a detailed bio (look for year/experience patterns)
    author_sections = soup.find_all(
        ["div", "section", "aside"],
        class_=re.compile(r"author|bio|about-author|byline|contributor", re.I),
    )
    has_detailed_bio = False
    for section in author_sections:
        bio_text = section.get_text(strip=True)
        # Detailed bio: > 50 characters with numbers or years
        if len(bio_text) > 50 and re.search(r"\b\d+\s*(?:years?|anni|experience)\b", bio_text, re.I):
            has_detailed_bio = True
            break

    if has_detailed_bio:
        score += 1

    # HTTPS (look for canonical or og:url starting with https)
    canonical = soup.find("link", attrs={"rel": "canonical"})
    og_url = soup.find("meta", attrs={"property": "og:url"})
    is_https = False
    for tag in [canonical, og_url]:
        if tag:
            url_val = tag.get("href") or tag.get("content") or ""
            if url_val.startswith("https://"):
                is_https = True
                break
    if is_https:
        score += 1

    return MethodScore(
        name="eeat_signals",
        label="E-E-A-T Signals",
        detected=trust_count >= 2 or (has_detailed_bio and trust_count >= 1),
        score=min(score, 5),
        max_score=5,
        impact="+15%",
        details={
            "trust_links": trust_links,
            "trust_link_count": trust_count,
            "has_detailed_bio": has_detailed_bio,
            "is_https": is_https,
        },
    )


# ─── Entity Resolution Friendliness (#373) ────────────────────────────────────


def detect_entity_resolution(soup) -> MethodScore:
    """Detect how easily LLMs can disambiguate entities on the page (#373).

    Checks:
    1. Entities are defined at first use (explicit "X is..." patterns)
    2. Schema.org provides @type + name + description for main entity
    3. Consistent entity naming (no conflicting references)
    4. sameAs links for disambiguation
    """
    score = 0
    has_schema_entity = False
    has_sameas = False
    has_definition = False
    entity_types_found: list[str] = []

    # 1. Check JSON-LD for well-typed entities with description
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Support @graph arrays
                graph = item.get("@graph", [])
                if graph and isinstance(graph, list):
                    items.extend(graph)
                    continue
                entity_type = item.get("@type")
                name = item.get("name")
                desc = item.get("description")
                if entity_type and name:
                    has_schema_entity = True
                    if isinstance(entity_type, list):
                        entity_types_found.extend(entity_type)
                    else:
                        entity_types_found.append(str(entity_type))
                    if desc:
                        score += 1  # well-described entity
                # sameAs check (same item may have both @type and sameAs)
                same_as = item.get("sameAs", [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                if isinstance(same_as, list) and len(same_as) >= 2:
                    has_sameas = True
        except (json.JSONDecodeError, TypeError):
            continue

    if has_schema_entity:
        score += 1
    if has_sameas:
        score += 1

    # 2. Check first paragraph for entity definition pattern
    body = soup.find("body")
    if body:
        first_p = body.find("p")
        if first_p:
            text = first_p.get_text(strip=True)
            if re.search(
                r"\b(?:is|are|refers?\s+to|è|sono|significa)\s+"
                r"(?:a|an|the|un|una|il|la|lo|one\s+of|defined\s+as)",
                text,
                re.I,
            ):
                has_definition = True
                score += 1

    return MethodScore(
        name="entity_resolution",
        label="Entity Resolution Friendliness",
        detected=score >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "has_schema_entity": has_schema_entity,
            "has_sameas": has_sameas,
            "has_definition": has_definition,
            "entity_types": entity_types_found[:5],
        },
    )


# ─── Knowledge Graph Density (#366) ──────────────────────────────────────────


def detect_kg_density(soup, clean_text: str | None = None) -> MethodScore:
    """Detect explicit entity relationships for knowledge graph extraction (#366).

    Measures how many explicit relationship statements (e.g., "X is a Y",
    "founded by Z", "located in W") exist in the content, making it easier
    for LLMs to build structured knowledge from the page.
    """
    body_text = clean_text or _get_clean_text(soup)
    if not body_text or len(body_text) < 50:
        return MethodScore(
            name="kg_density",
            label="Knowledge Graph Density",
            max_score=4,
            impact="+10%",
        )

    # Count relationship pattern matches
    matches = _KG_RELATION_RE.findall(body_text)
    relation_count = len(matches)

    # Normalize by content length (per 500 words)
    word_count = len(body_text.split())
    density = (relation_count / word_count) * 500 if word_count > 0 else 0

    # Check for structured data relationships too (schema.org)
    schema_relations = 0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                graph = item.get("@graph", [])
                if graph and isinstance(graph, list):
                    items.extend(graph)
                    continue
                # Count relationship properties
                for key in (
                    "author",
                    "creator",
                    "publisher",
                    "founder",
                    "parentOrganization",
                    "memberOf",
                    "worksFor",
                    "location",
                    "address",
                    "brand",
                    "manufacturer",
                    "isPartOf",
                    "hasPart",
                    "mainEntity",
                ):
                    if item.get(key):
                        schema_relations += 1
        except (json.JSONDecodeError, TypeError):
            continue

    # Score: content relations + schema relations
    if density >= 8 or (density >= 5 and schema_relations >= 3):
        score = 4
    elif density >= 5 or (density >= 3 and schema_relations >= 2):
        score = 3
    elif density >= 3 or schema_relations >= 2:
        score = 2
    elif relation_count >= 2 or schema_relations >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="kg_density",
        label="Knowledge Graph Density",
        detected=score >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "relation_count": relation_count,
            "density_per_500w": round(density, 1),
            "schema_relations": schema_relations,
            "word_count": word_count,
        },
    )


# ─── Retrieval Trigger Patterns (#374) ───────────────────────────────────────


def detect_retrieval_triggers(soup, clean_text: str | None = None) -> MethodScore:
    """Detect phrases that trigger RAG retrieval in LLM pipelines (#374).

    RAG systems rank chunks by relevance to user queries. Content with
    explicit trigger phrases (e.g., "research shows", "best practice",
    "how to", "compared to") is more likely to be retrieved and cited.
    """
    body_text = clean_text or _get_clean_text(soup)
    if not body_text or len(body_text) < 50:
        return MethodScore(
            name="retrieval_triggers",
            label="Retrieval Trigger Patterns",
            max_score=4,
            impact="+10%",
        )

    # Count unique trigger types found
    matches = _RETRIEVAL_TRIGGER_RE.findall(body_text)
    trigger_count = len(matches)
    unique_triggers = len({m.lower().strip() for m in matches})

    # Normalize by content length (per 500 words)
    word_count = len(body_text.split())
    density = (trigger_count / word_count) * 500 if word_count > 0 else 0

    # Check for question-format headings (strong retrieval triggers)
    question_headings = 0
    for h in soup.find_all(re.compile(r"^h[1-6]$")):
        text = h.get_text(strip=True)
        if text.endswith("?") or re.match(r"(?:how|what|why|when|where|which|who)\b", text, re.I):
            question_headings += 1

    # Score: variety of triggers + density + question headings
    if unique_triggers >= 8 and question_headings >= 2:
        score = 4
    elif unique_triggers >= 6 or (unique_triggers >= 4 and question_headings >= 2):
        score = 3
    elif unique_triggers >= 4 or (unique_triggers >= 2 and question_headings >= 1):
        score = 2
    elif unique_triggers >= 2 or question_headings >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="retrieval_triggers",
        label="Retrieval Trigger Patterns",
        detected=score >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "trigger_count": trigger_count,
            "unique_triggers": unique_triggers,
            "density_per_500w": round(density, 1),
            "question_headings": question_headings,
        },
    )

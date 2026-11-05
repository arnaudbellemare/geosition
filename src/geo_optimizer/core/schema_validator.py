"""
JSON-LD Schema Validator.

Validates schema.org JSON-LD structures for common types.
"""

from __future__ import annotations

import json

from geo_optimizer.models.config import SCHEMA_ORG_REQUIRED


def _valid_context(context) -> tuple[bool, str | None]:
    valid_contexts = ["https://schema.org", "http://schema.org"]
    if isinstance(context, str):
        if context not in valid_contexts:
            return False, f"@context must be 'https://schema.org', got '{context}'"
        return True, None
    if isinstance(context, list):
        if not context or context[0] not in valid_contexts:
            first = context[0] if context else "empty list"
            return False, f"@context[0] must be 'https://schema.org', got '{first}'"
        return True, None
    return False, f"@context must be string or array, got {type(context).__name__}"


def _schema_types(schema_dict: dict) -> list[str]:
    schema_type_field = schema_dict.get("@type")
    if isinstance(schema_type_field, list):
        return [str(item) for item in schema_type_field if item]
    return [str(schema_type_field)] if schema_type_field else []


def _iter_schema_nodes(data: object) -> list[tuple[dict, object]]:
    pending: list[tuple[object, object]] = [(data, None)]
    nodes: list[tuple[dict, object]] = []

    while pending:
        item, inherited_context = pending.pop(0)
        if isinstance(item, list):
            pending.extend((child, inherited_context) for child in item)
            continue
        if not isinstance(item, dict):
            continue

        context = item.get("@context", inherited_context)
        graph = item.get("@graph")
        if isinstance(graph, list):
            pending.extend((child, context) for child in graph)
        if item.get("@type"):
            nodes.append((item, context))

    return nodes


def validate_jsonld(
    schema_dict: dict | list,
    schema_type: str | None = None,
    strict: bool = False,
) -> tuple[bool, str | None]:
    """
    Validate a JSON-LD schema structure.

    Args:
        schema_dict: The parsed JSON-LD schema
        schema_type: Expected schema type (e.g., 'website', 'faqpage')
        strict: If True, fail on warnings. If False, only fail on critical errors.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(schema_dict, (dict, list)):
        return False, f"Schema must be a dict or list, got {type(schema_dict).__name__}"

    nodes = _iter_schema_nodes(schema_dict)
    if not nodes:
        if isinstance(schema_dict, dict) and not schema_dict.get("@context"):
            return False, "Missing required field: @context"
        return False, "Missing required field: @type"

    if schema_type:
        schema_type_normalized = schema_type.lower()
        matching_nodes = [
            (node, context)
            for node, context in nodes
            if any(item.lower() == schema_type_normalized for item in _schema_types(node))
        ]
        if not matching_nodes:
            found = sorted({item for node, _ in nodes for item in _schema_types(node)})
            found_label = ", ".join(found) if found else "none"
            return False, f"Expected @type '{schema_type}', got '{found_label}'"
        nodes_to_validate = matching_nodes
    else:
        nodes_to_validate = nodes

    node, context = nodes_to_validate[0]
    primary_types = _schema_types(node)
    primary_type = primary_types[0] if primary_types else ""

    if not primary_type:
        return False, "@type is empty"

    if not context:
        return False, "Missing required field: @context"
    valid_context, context_error = _valid_context(context)
    if not valid_context:
        return False, context_error

    if schema_type:
        required_fields = SCHEMA_ORG_REQUIRED.get(schema_type.lower(), ["@context", "@type"])
        missing_fields = [f for f in required_fields if f not in node and not (f == "@context" and context)]
        if missing_fields:
            return False, (f"Missing required fields for {primary_type}: {', '.join(missing_fields)}")

    url_fields = ["url", "sameAs", "logo", "image"]
    for node_to_check, _ in nodes_to_validate:
        for fld in url_fields:
            value = node_to_check.get(fld)
            if value:
                if isinstance(value, str):
                    urls_to_check = [value]
                elif isinstance(value, list):
                    urls_to_check = value
                else:
                    continue

                for url in urls_to_check:
                    if isinstance(url, str) and not url.startswith(("http://", "https://", "/")) and strict:
                        return False, (
                            f"Invalid URL format in '{fld}': '{url}' (must start with http://, https://, or /)"
                        )

    return True, None


def validate_jsonld_string(
    json_string: str,
    schema_type: str | None = None,
    strict: bool = False,
) -> tuple[bool, str | None]:
    """Validate a JSON-LD schema from a string."""
    try:
        schema_dict = json.loads(json_string)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    return validate_jsonld(schema_dict, schema_type, strict)


def get_required_fields(schema_type: str) -> list[str]:
    """Get list of required fields for a schema type."""
    return SCHEMA_ORG_REQUIRED.get(schema_type.lower(), ["@context", "@type"])

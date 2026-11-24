"""Generate review-only service markup and enquiry test plans."""

from __future__ import annotations

import json
from pathlib import Path

import click

from geo_optimizer.core.commerce_services import prepare_services, review_from_audit


@click.command(name="commerce-service-prepare")
@click.option("--audit", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Site-audit JSON input.")
@click.option(
    "--review", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Edited service-review JSON input."
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(path_type=Path),
    help="New output directory; never overwrites an existing directory.",
)
def commerce_service_prepare(audit: Path | None, review: Path | None, output_dir: Path) -> None:
    """Prepare service JSON-LD drafts and enquiry-journey test plans."""
    if bool(audit) == bool(review):
        raise click.UsageError("Provide exactly one of --audit or --review.")
    try:
        data = json.loads((audit or review).read_text(encoding="utf-8"))
        prepared = prepare_services(review_from_audit(data) if audit else data)
        output_dir.mkdir(parents=True, exist_ok=False)
        for name, content in (
            ("service-review.json", prepared.review),
            ("validation.json", prepared.validation),
            ("service-structured-data.draft.jsonld", prepared.structured_data),
        ):
            (output_dir / name).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "enquiry-test-plan.md").write_text(_test_plan(prepared.review), encoding="utf-8")
        (output_dir / "README.md").write_text(_GUIDE, encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Prepared {len(prepared.review['services'])} service candidates and {len(prepared.review['journeys'])} enquiry signals. See {output_dir / 'README.md'}."
    )


def _safe(value):
    return str(value).replace("\r", " ").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


def _test_plan(review):
    coverage = review.get("coverage", {})
    lines = [
        "# Enquiry journey — manual test plan",
        "",
        "These are observed controls, not verified journeys. Do not submit a real enquiry without explicit authorization. Perform the inspection without sending a message or creating a transaction.",
        "",
        f"Audit date: {_safe(review.get('audit_date', 'unknown'))}. Pages audited: {coverage.get('pages_audited', 'unknown')}; discovered pages pending: {coverage.get('pending', 'unknown')}.",
        "",
        "## Signals to review",
        "",
    ]
    for index, item in enumerate(review["journeys"], 1):
        status = (
            "operator marked tested; outcome not independently verified"
            if item.get("tested") is True
            else "not verified"
        )
        lines.extend(
            [
                f"### {index}. {_safe(item.get('label', 'Enquiry'))}",
                "",
                f"- Element: {_safe(item.get('element', 'unknown'))}",
                f"- Observed destination: {_safe(item.get('observed_url') or 'none captured; inspect the control')}",
                f"- Status: {status}",
            ]
        )
        for source in item.get("evidence_pages", []):
            lines.append(f"- Observed on: {_safe(source)}")
        lines.append("")
    if not review["journeys"]:
        lines.extend(["No enquiry control was observed on the audited pages; this does not prove one is absent.", ""])
    lines.extend(
        [
            "## Steps for the owner or authorized operator",
            "",
            "1. Review each source page and the corresponding destination in the relevant language; inspect without sending an enquiry.",
            "2. Check that the service, required fields, privacy notice, handoff and expected response are clear; document any inaccessible or confusing step.",
            "3. If an end-to-end submission is needed, arrange an explicitly authorized test recipient or sandbox with the owner first. Record the outcome without including customer personal data.",
            "4. Edit the matching `tested` and `outcome_notes` fields in `service-review.json` only after the authorized check, then regenerate into a new directory.",
            "",
            "Browser access, real deliveries, provider eligibility and the final customer outcome were not verified by this generator.",
            "",
        ]
    )
    return "\n".join(lines)


_GUIDE = """# Service and enquiry preparation — owner review draft

These files use audit observations, not verified business details. Names with identical spelling are grouped across source pages; the same label could refer to different offerings, and translations or variants may describe the same offering. Review and merge or split candidates manually.

1. Edit `service-review.json`: confirm each service name and add its actual description, service page URL, area served and provider name. Set `owner_reviewed` to `true` only after the business confirms the information. Add no guessed prices, availability or promises.
2. Examine `enquiry-test-plan.md` and perform the non-submitting checks. An observed button or link does not establish a working journey. Arrange an explicitly authorized sandbox or test recipient before any real submission. Record only the outcome, not customer personal information.
3. Regenerate using `geo commerce-service-prepare --review path/to/service-review.json --output-dir path/to/new-draft`. Inspect `validation.json`. These are internal completeness checks, not independent confirmation, provider eligibility checks, or schema conformance validation.
4. Review `service-structured-data.draft.jsonld` against existing structured data first: do not blindly add duplicate Service markup. Confirm all fields against the actual page, use an HTML-safe serializer when embedding, and validate through an appropriate structured-data validator.

Guidance: https://schema.org/Service and https://developers.google.com/search/docs/appearance/structured-data/sd-policies. No website, business account, or enquiry is changed by this tool.
"""

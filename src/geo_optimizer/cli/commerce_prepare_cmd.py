"""Generate local, review-only product structured-data and feed worksheets."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import click

from geo_optimizer.core.commerce_preparation import catalog_from_audit, prepare_catalog

_FIELDS = (
    "name",
    "item_id",
    "product_url",
    "description",
    "image_url",
    "price",
    "currency",
    "availability",
    "owner_reviewed",
    "rights_confirmed",
    "observed_price_text",
    "source_url",
)


def _cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@click.command(name="commerce-prepare")
@click.option(
    "--audit",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Site-audit JSON input.",
)
@click.option(
    "--catalog",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Edited review-catalog JSON input.",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(path_type=Path),
    help="New output directory; never overwrites an existing directory.",
)
def commerce_prepare(audit: Path | None, catalog: Path | None, output_dir: Path) -> None:
    """Prepare review-only catalog, JSON-LD draft, and feed worksheet."""
    if bool(audit) == bool(catalog):
        raise click.UsageError("Provide exactly one of --audit or --catalog.")
    try:
        data = json.loads((audit or catalog).read_text(encoding="utf-8"))
        review = catalog_from_audit(data) if audit else data
        prepared = prepare_catalog(review)
        output_dir.mkdir(parents=True, exist_ok=False)
        (output_dir / "catalog-review.json").write_text(
            json.dumps(prepared.catalog, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "validation.json").write_text(
            json.dumps(prepared.validation, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "product-structured-data.draft.jsonld").write_text(
            json.dumps(prepared.structured_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with (output_dir / "feed-worksheet.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=_FIELDS)
            writer.writeheader()
            for item in prepared.catalog["items"]:
                writer.writerow({field: _cell(item.get(field, "")) for field in _FIELDS})
        (output_dir / "README.md").write_text(_GUIDE, encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        raise click.ClickException(str(exc)) from exc
    issues = sum(bool(item["issues"]) for item in prepared.validation["items"])
    click.echo(
        f"Prepared {len(prepared.catalog['items'])} draft items; {issues} require review. See {output_dir / 'README.md'}."
    )


_GUIDE = """# Product preparation — draft for owner review

These files are review drafts, not a provider feed and not ready to publish. Audit cards and observed prices are unverified, may be stale or duplicated, and can include unavailable items or placeholders. No feed was submitted and no website was changed.

1. Open `catalog-review.json` and check each item against the current merchant catalog. Remove duplicates and items not for sale; supply a stable item ID, the actual product URL, accurate description, authorized image URL, current price (decimal), currency (three uppercase letters), and availability (`InStock`, `OutOfStock`, `PreOrder`, `BackOrder`, or `Discontinued`).
2. Confirm product details and image rights with the owner. Set `owner_reviewed` and `rights_confirmed` to `true` only after that review. `observed_price_text` is evidence, not a verified price; do not treat it as the current price.
3. Run `geo commerce-prepare --catalog path/to/catalog-review.json --output-dir path/to/new-draft` to regenerate artifacts. Read `validation.json` for per-item internal completeness issues. Passing these checks does not establish provider schema compliance, eligibility, ownership, correct prices, or publication readiness.
4. Review `product-structured-data.draft.jsonld` against the actual product pages. Before embedding JSON-LD in HTML, use an HTML-safe serializer; never copy untrusted text directly into a script tag. Validate with the relevant structured-data tooling and ensure data matches the page.
5. `feed-worksheet.csv` is an operator worksheet, not a provider feed. Map the reviewed source data to the current provider schema, validate every required field, confirm merchant onboarding and permission, and review the final feed before any submission.

Guidance: https://developers.openai.com/commerce/guides/submit-product-feeds and https://developers.google.com/search/docs/appearance/structured-data/product.
"""

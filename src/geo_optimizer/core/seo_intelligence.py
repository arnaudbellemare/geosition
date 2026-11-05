"""Classic SEO intelligence providers and local storage utilities."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from geo_optimizer.models.config import GEO_OPTIMIZER_HOME
from geo_optimizer.models.results import (
    BacklinkAnalysisResult,
    BacklinkHistoryPoint,
    BacklinkRecord,
    DomainAnalysisResult,
    DomainCompetitor,
    DomainKeyword,
    DomainTopPage,
    KeywordGap,
    KeywordMetric,
    KeywordResearchResult,
    LighthouseMetric,
    LighthouseResult,
    RankSnapshot,
    RankTrackingResult,
    ReferringDomainRecord,
    SerpCrowdednessResult,
    TrackedKeyword,
)
from geo_optimizer.utils.http import fetch_url
from geo_optimizer.utils.validators import validate_public_url

KEYWORD_LISTS_DIR = GEO_OPTIMIZER_HOME / "keyword-lists"
RANK_TRACKING_DB_PATH = GEO_OPTIMIZER_HOME / "rank-tracking.db"

_COMMERCIAL_TERMS = {
    "best",
    "pricing",
    "price",
    "cost",
    "buy",
    "service",
    "services",
    "agency",
    "software",
    "tool",
    "tools",
    "alternative",
    "alternatives",
    "vs",
}
_TRANSACTIONAL_TERMS = {"buy", "order", "book", "hire", "quote", "near me", "demo", "trial"}
_NAVIGATIONAL_TERMS = {"login", "sign in", "homepage", "contact", "support"}
_SEARCH_ENGINE_DOMAINS = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "search.yahoo.com",
}


class KeywordMetricsProvider(Protocol):
    """Provider contract for keyword metrics."""

    name: str

    def research(self, seed: str, limit: int = 20) -> list[KeywordMetric]:
        """Return keyword metrics for seed-derived ideas."""


class DomainAnalysisProvider(Protocol):
    """Provider contract for domain intelligence."""

    name: str

    def analyze(self, url: str, competitors: list[str] | None = None) -> DomainAnalysisResult:
        """Return a domain profile and keyword gap analysis."""


class BacklinkProvider(Protocol):
    """Provider contract for backlink intelligence."""

    name: str

    def analyze(self, domain: str) -> BacklinkAnalysisResult:
        """Return backlink, referring-domain, anchor, and new/lost history data."""


def research_keywords(
    seed: str,
    limit: int = 20,
    provider: KeywordMetricsProvider | None = None,
    save_list: str | None = None,
    csv_path: str | None = None,
) -> KeywordResearchResult:
    """Research keyword metrics and optionally persist/export them."""
    provider = provider or LocalKeywordMetricsProvider()
    metrics = provider.research(seed, limit=limit)
    result = KeywordResearchResult(checked=True, seed=seed, provider=provider.name, metrics=metrics)

    if provider.name == "local-estimate":
        result.warnings.append(
            "Using deterministic local estimates. Configure a real KeywordMetricsProvider for vendor data."
        )

    if save_list:
        result.saved_list_path = str(save_keyword_list(save_list, metrics))
    if csv_path:
        result.csv_path = str(export_keyword_metrics_csv(csv_path, metrics))
    return result


def save_keyword_list(list_name: str, metrics: list[KeywordMetric]) -> Path:
    """Save keyword metrics to a named local CSV list."""
    KEYWORD_LISTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in list_name.strip()).strip("-")
    path = KEYWORD_LISTS_DIR / f"{safe_name or 'keywords'}.csv"
    export_keyword_metrics_csv(str(path), metrics)
    return path


def export_keyword_metrics_csv(path: str, metrics: list[KeywordMetric]) -> Path:
    """Export keyword metrics as CSV."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["keyword", "volume", "cpc", "competition", "difficulty", "intent", "trend", "source"],
        )
        writer.writeheader()
        for metric in metrics:
            row = asdict(metric)
            row["trend"] = " ".join(str(item) for item in metric.trend)
            writer.writerow(row)
    return out_path


class LocalKeywordMetricsProvider:
    """Deterministic zero-network keyword metric estimator."""

    name = "local-estimate"

    def research(self, seed: str, limit: int = 20) -> list[KeywordMetric]:
        """Generate seed variants with deterministic metric estimates."""
        ideas = _keyword_ideas(seed)
        return [_estimate_keyword_metric(keyword) for keyword in ideas[: max(1, limit)]]


def _keyword_ideas(seed: str) -> list[str]:
    base = " ".join(seed.lower().split())
    modifiers = [
        "",
        "best",
        "pricing",
        "near me",
        "software",
        "services",
        "alternatives",
        "comparison",
        "how to",
        "guide",
        "cost",
        "agency",
        "tools",
        "for small business",
        "examples",
    ]
    ideas = []
    for modifier in modifiers:
        if not modifier:
            ideas.append(base)
        elif modifier in {"best", "how to"}:
            ideas.append(f"{modifier} {base}")
        else:
            ideas.append(f"{base} {modifier}")
    return list(dict.fromkeys(item.strip() for item in ideas if item.strip()))


def _estimate_keyword_metric(keyword: str) -> KeywordMetric:
    digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    words = keyword.split()
    commercial = sum(1 for word in words if word in _COMMERCIAL_TERMS)
    volume = 20 + (seed % 9800)
    if len(words) >= 4:
        volume = max(10, int(volume * 0.35))
    cpc = round(((seed >> 4) % 2200) / 100 + commercial * 0.75, 2)
    competition = round(min(1.0, 0.15 + ((seed >> 12) % 70) / 100 + commercial * 0.07), 2)
    difficulty = min(100, int(competition * 70) + min(25, volume // 350) + commercial * 4)
    intent = _classify_intent(keyword)
    trend = [max(0, min(100, 45 + ((seed >> (i % 16)) % 31) - 15 + i)) for i in range(12)]
    return KeywordMetric(
        keyword=keyword,
        volume=volume,
        cpc=cpc,
        competition=competition,
        difficulty=difficulty,
        intent=intent,
        trend=trend,
        source="local-estimate",
    )


def _classify_intent(keyword: str) -> str:
    lowered = keyword.lower()
    if any(term in lowered for term in _TRANSACTIONAL_TERMS):
        return "transactional"
    if any(term in lowered for term in _NAVIGATIONAL_TERMS):
        return "navigational"
    if any(term in lowered for term in _COMMERCIAL_TERMS):
        return "commercial"
    return "informational"


def score_serp_crowdedness(
    keyword: str,
    organic_results: int,
    competitor_domains: list[str],
    serp_features: list[str] | None = None,
    ads_count: int = 0,
) -> SerpCrowdednessResult:
    """Compute a 0-100 SERP crowdedness score."""
    features = serp_features or []
    unique_domains = len(set(competitor_domains))
    score = (
        min(35, organic_results * 3) + min(25, unique_domains * 4) + min(25, len(features) * 6) + min(15, ads_count * 5)
    )
    if score >= 75:
        label = "very crowded"
    elif score >= 50:
        label = "crowded"
    elif score >= 25:
        label = "moderate"
    else:
        label = "open"
    factors = [
        f"{organic_results} organic results analyzed",
        f"{unique_domains} unique competing domains",
    ]
    if features:
        factors.append(f"SERP features present: {', '.join(features)}")
    if ads_count:
        factors.append(f"{ads_count} paid result blocks detected")
    return SerpCrowdednessResult(
        checked=True,
        keyword=keyword,
        score=min(100, score),
        label=label,
        organic_results=organic_results,
        ads_count=ads_count,
        serp_features=features,
        competitor_domains=competitor_domains,
        factors=factors,
    )


def analyze_domain(
    url: str,
    competitors: list[str] | None = None,
    provider: DomainAnalysisProvider | None = None,
) -> DomainAnalysisResult:
    """Profile a domain and estimate keyword gaps."""
    provider = provider or LocalDomainAnalysisProvider()
    return provider.analyze(url, competitors=competitors)


class LocalDomainAnalysisProvider:
    """Zero-network domain profiler using the target page and optional competitors."""

    name = "local-estimate"

    def analyze(self, url: str, competitors: list[str] | None = None) -> DomainAnalysisResult:
        """Return local estimates for authority, traffic, pages, keywords, and gaps."""
        ok, err = validate_public_url(url)
        if not ok:
            return DomainAnalysisResult(checked=False, domain=_domain_from_url(url), warnings=[err or "invalid URL"])

        response, fetch_err = fetch_url(url)
        if fetch_err or response is None:
            return DomainAnalysisResult(
                checked=False,
                domain=_domain_from_url(url),
                provider=self.name,
                warnings=[fetch_err or "unable to fetch domain"],
            )

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        domain = _domain_from_url(url)
        keywords = [_estimate_keyword_metric(term) for term in _extract_domain_terms(text)[:12]]
        ranked = [
            DomainKeyword(keyword=item.keyword, position=(i % 10) + 1, volume=item.volume, url=url)
            for i, item in enumerate(keywords)
        ]
        authority = _estimate_authority(domain, soup, len(text.split()))
        traffic = sum(max(0, int(item.volume * (0.35 / max(item.position, 1)))) for item in ranked)
        top_pages = [
            DomainTopPage(
                url=url,
                title=_page_title(soup) or domain,
                estimated_traffic=traffic,
                keyword_count=len(ranked),
            )
        ]

        comp_results = []
        gap_results = []
        for comp_url in competitors or []:
            comp_domain = _domain_from_url(comp_url)
            comp_authority = _estimate_authority(comp_domain, None, 0)
            comp_results.append(
                DomainCompetitor(
                    domain=comp_domain, overlap_keywords=max(1, len(ranked) // 3), authority=comp_authority
                )
            )
            for metric in [
                _estimate_keyword_metric(f"{ranked[0].keyword} {suffix}")
                for suffix in ("pricing", "alternatives")
                if ranked
            ]:
                gap_results.append(
                    KeywordGap(
                        keyword=metric.keyword,
                        competitor_domain=comp_domain,
                        competitor_position=1 + (metric.difficulty % 5),
                        volume=metric.volume,
                        difficulty=metric.difficulty,
                    )
                )

        return DomainAnalysisResult(
            checked=True,
            domain=domain,
            provider=self.name,
            authority=authority,
            estimated_traffic=traffic,
            top_pages=top_pages,
            ranked_keywords=ranked,
            competitors=comp_results,
            keyword_gaps=gap_results,
            warnings=["Using local estimates. Configure a DomainAnalysisProvider for vendor-grade traffic data."],
        )


def analyze_backlinks(domain: str, provider: BacklinkProvider | None = None) -> BacklinkAnalysisResult:
    """Analyze backlinks with a vendor-neutral provider."""
    provider = provider or CsvBacklinkProvider.from_env() or LocalBacklinkDiscoveryProvider()
    return provider.analyze(domain)


class CsvBacklinkProvider:
    """Backlink provider reading vendor-neutral rows from a CSV file."""

    name = "csv"

    def __init__(self, path: str):
        self.path = Path(path)

    @classmethod
    def from_env(cls) -> CsvBacklinkProvider | None:
        """Build provider from GEO_BACKLINK_CSV when configured."""
        path = os.environ.get("GEO_BACKLINK_CSV")
        return cls(path) if path else None

    def analyze(self, domain: str) -> BacklinkAnalysisResult:
        """Load backlink rows for a target domain."""
        if not self.path.exists():
            return BacklinkAnalysisResult(
                checked=False,
                domain=domain,
                provider=self.name,
                warnings=[f"CSV file not found: {self.path}"],
            )

        target = domain.lower().replace("www.", "")
        backlinks = []
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                target_url = row.get("target_url", "")
                if target and target not in target_url.lower():
                    continue
                source_url = row.get("source_url", "")
                backlinks.append(
                    BacklinkRecord(
                        source_url=source_url,
                        source_domain=_domain_from_url(source_url),
                        target_url=target_url,
                        anchor=row.get("anchor", ""),
                        link_strength=int(float(row.get("link_strength") or 0)),
                        first_seen=row.get("first_seen", ""),
                        last_seen=row.get("last_seen", ""),
                        status=row.get("status", "live") or "live",
                    )
                )
        return _summarize_backlinks(domain, self.name, backlinks)


class EmptyBacklinkProvider:
    """Provider seam placeholder when no backlink vendor or CSV is configured."""

    name = "local-empty"

    def analyze(self, domain: str) -> BacklinkAnalysisResult:
        """Return an empty but checked backlink result."""
        return BacklinkAnalysisResult(
            checked=True,
            domain=domain,
            provider=self.name,
            warnings=[
                "No backlink provider configured. Set GEO_BACKLINK_CSV or pass a BacklinkProvider implementation."
            ],
        )


class LocalBacklinkDiscoveryProvider:
    """Discover candidate backlinks/mentions from public search result pages."""

    name = "local-discovery"

    def analyze(self, domain: str) -> BacklinkAnalysisResult:
        """Return candidate backlink records found from off-site domain mentions."""
        target = domain.lower().replace("www.", "")
        search_url = "https://html.duckduckgo.com/html/?q=" + quote_plus(f'"{target}" -site:{target}') + "&kl=us-en"
        response, err = fetch_url(search_url, timeout=15)
        if err or response is None:
            empty = EmptyBacklinkProvider().analyze(domain)
            empty.provider = self.name
            empty.warnings = [
                "Could not run local backlink discovery. Configure GEO_BACKLINK_CSV or a BacklinkProvider for full data.",
                err or "search fetch failed",
            ]
            return empty

        soup = BeautifulSoup(response.text, "html.parser")
        backlinks: list[BacklinkRecord] = []
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = _clean_search_result_url(link.get("href", ""))
            source_domain = _domain_from_url(href)
            if not href.startswith(("http://", "https://")):
                continue
            if source_domain in _SEARCH_ENGINE_DOMAINS:
                continue
            if not source_domain or source_domain == target or source_domain.endswith("." + target):
                continue
            if href in seen:
                continue
            seen.add(href)
            anchor = link.get_text(" ", strip=True)
            backlinks.append(
                BacklinkRecord(
                    source_url=href,
                    source_domain=source_domain,
                    target_url=f"https://{target}",
                    anchor=anchor[:120],
                    link_strength=_estimate_authority(source_domain, None, 0),
                    first_seen="",
                    last_seen=_now()[:10],
                    status="candidate",
                )
            )
            if len(backlinks) >= 25:
                break

        result = _summarize_backlinks(domain, self.name, backlinks)
        result.warnings.append(
            "Local discovery lists candidate off-site mentions/backlinks, not a complete backlink index. "
            "Use GEO_BACKLINK_CSV or a vendor BacklinkProvider for verified new/lost link history."
        )
        return result


def _summarize_backlinks(domain: str, provider: str, backlinks: list[BacklinkRecord]) -> BacklinkAnalysisResult:
    referring_counter = Counter(item.source_domain for item in backlinks if item.source_domain)
    anchor_counter = Counter((item.anchor or "").strip().lower() or "(empty)" for item in backlinks)
    referring = [
        ReferringDomainRecord(
            domain=ref_domain,
            backlinks=count,
            authority=_estimate_authority(ref_domain, None, 0),
        )
        for ref_domain, count in referring_counter.most_common()
    ]
    history_by_date: dict[str, dict[str, int]] = {}
    for item in backlinks:
        date = (item.last_seen or item.first_seen or "")[:10]
        if not date:
            continue
        bucket = history_by_date.setdefault(date, {"new": 0, "lost": 0})
        if item.status == "lost":
            bucket["lost"] += 1
        else:
            bucket["new"] += 1
    history = [
        BacklinkHistoryPoint(date=date, new_links=values["new"], lost_links=values["lost"])
        for date, values in sorted(history_by_date.items())
    ]
    return BacklinkAnalysisResult(
        checked=True,
        domain=domain,
        provider=provider,
        backlinks=backlinks,
        referring_domains=referring,
        anchors=dict(anchor_counter.most_common()),
        new_lost_history=history,
    )


class RankTracker:
    """SQLite-backed organic rank tracker."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or RANK_TRACKING_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracked_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(keyword, url)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rank_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    rank INTEGER,
                    checked_at TEXT NOT NULL,
                    search_engine TEXT NOT NULL
                )
                """
            )

    def add_keyword(self, keyword: str, url: str) -> TrackedKeyword:
        """Add a tracked keyword and target URL."""
        ok, err = validate_public_url(url)
        if not ok:
            raise ValueError(err or "invalid URL")
        domain = _domain_from_url(url)
        created_at = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO tracked_keywords (keyword, url, domain, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (keyword, url, domain, created_at),
            )
        return TrackedKeyword(keyword=keyword, url=url, domain=domain, created_at=created_at)

    def list_keywords(self) -> list[TrackedKeyword]:
        """Return tracked keyword configurations."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT keyword, url, domain, created_at FROM tracked_keywords ORDER BY created_at DESC, keyword ASC"
            ).fetchall()
        return [
            TrackedKeyword(
                keyword=row["keyword"],
                url=row["url"],
                domain=row["domain"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def snapshot_all(self, search_engine: str = "google") -> RankTrackingResult:
        """Fetch and store one rank snapshot for every tracked keyword."""
        snapshots = [
            self.snapshot_keyword(item.keyword, item.url, search_engine=search_engine) for item in self.list_keywords()
        ]
        return self.analytics(snapshots=snapshots)

    def snapshot_keyword(self, keyword: str, url: str, search_engine: str = "google") -> RankSnapshot:
        """Fetch and store one rank snapshot for a keyword/URL pair."""
        domain = _domain_from_url(url)
        rank = _lookup_rank(keyword, domain)
        snapshot = RankSnapshot(
            keyword=keyword, url=url, domain=domain, rank=rank, checked_at=_now(), search_engine=search_engine
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rank_snapshots (keyword, url, domain, rank, checked_at, search_engine)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.keyword,
                    snapshot.url,
                    snapshot.domain,
                    snapshot.rank,
                    snapshot.checked_at,
                    snapshot.search_engine,
                ),
            )
        return snapshot

    def analytics(self, snapshots: list[RankSnapshot] | None = None) -> RankTrackingResult:
        """Return tracked keywords, snapshots, and aggregate rank analytics."""
        tracked = self.list_keywords()
        if snapshots is None:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT keyword, url, domain, rank, checked_at, search_engine
                    FROM rank_snapshots
                    ORDER BY checked_at DESC
                    LIMIT 200
                    """
                ).fetchall()
            snapshots = [
                RankSnapshot(
                    keyword=row["keyword"],
                    url=row["url"],
                    domain=row["domain"],
                    rank=row["rank"],
                    checked_at=row["checked_at"],
                    search_engine=row["search_engine"],
                )
                for row in rows
            ]
        ranks = [item.rank for item in snapshots if item.rank is not None]
        return RankTrackingResult(
            checked=True,
            db_path=str(self.db_path),
            tracked_keywords=tracked,
            snapshots=snapshots,
            average_rank=round(sum(ranks) / len(ranks), 2) if ranks else 0.0,
            best_rank=min(ranks) if ranks else None,
        )


def run_lighthouse_audit(
    url: str,
    provider: str = "pagespeed",
    api_key: str | None = None,
    report_path: str | None = None,
) -> LighthouseResult:
    """Run Lighthouse via PageSpeed Insights API or local lighthouse CLI."""
    ok, err = validate_public_url(url)
    if not ok:
        return LighthouseResult(checked=False, url=url, provider=provider, warnings=[err or "invalid URL"])

    if provider == "cli":
        return _run_lighthouse_cli(url, report_path=report_path)
    return _run_pagespeed_lighthouse(url, api_key=api_key or os.environ.get("PAGESPEED_API_KEY"))


def _run_pagespeed_lighthouse(url: str, api_key: str | None = None) -> LighthouseResult:
    query = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={quote_plus(url)}&category=performance&category=accessibility"
        "&category=best-practices&category=seo&strategy=mobile"
    )
    if api_key:
        query += f"&key={quote_plus(api_key)}"
    response, err = fetch_url(query, timeout=30)
    if err or response is None:
        return LighthouseResult(
            checked=False, url=url, provider="pagespeed", warnings=[err or "PageSpeed fetch failed"]
        )
    try:
        data = response.json()
    except ValueError:
        return LighthouseResult(
            checked=False, url=url, provider="pagespeed", warnings=["PageSpeed returned invalid JSON"]
        )
    return _parse_lighthouse_json(url, data, provider="pagespeed")


def _run_lighthouse_cli(url: str, report_path: str | None = None) -> LighthouseResult:
    executable = shutil.which("lighthouse")
    if not executable:
        return LighthouseResult(checked=False, url=url, provider="cli", warnings=["lighthouse CLI not found on PATH"])
    out_path = Path(report_path or (Path.cwd() / "lighthouse-report.json"))
    cmd = [
        executable,
        url,
        "--output=json",
        f"--output-path={out_path}",
        "--quiet",
        "--chrome-flags=--headless",
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return LighthouseResult(checked=False, url=url, provider="cli", warnings=[f"lighthouse failed: {exc}"])
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return LighthouseResult(checked=False, url=url, provider="cli", report_path=str(out_path), warnings=[str(exc)])
    result = _parse_lighthouse_json(url, {"lighthouseResult": data}, provider="cli")
    result.report_path = str(out_path)
    return result


def _parse_lighthouse_json(url: str, data: dict, provider: str) -> LighthouseResult:
    api_error = data.get("error")
    if isinstance(api_error, dict):
        message = str(api_error.get("message") or "PageSpeed API returned an error")
        status = str(api_error.get("status") or "")
        code = api_error.get("code")
        prefix = f"PageSpeed API error {code}" if code else "PageSpeed API error"
        if status:
            prefix = f"{prefix} ({status})"
        return LighthouseResult(checked=False, url=url, provider=provider, warnings=[f"{prefix}: {message}"])

    lighthouse = data.get("lighthouseResult") or {}
    if not lighthouse:
        return LighthouseResult(
            checked=False,
            url=url,
            provider=provider,
            warnings=["No lighthouseResult found in provider response."],
        )
    categories = lighthouse.get("categories") or {}
    audits = lighthouse.get("audits") or {}
    if not categories or not audits:
        return LighthouseResult(
            checked=False,
            url=url,
            provider=provider,
            warnings=["Incomplete Lighthouse response: missing categories or audits."],
        )
    metrics = []
    for audit_id, label in (
        ("first-contentful-paint", "First Contentful Paint"),
        ("largest-contentful-paint", "Largest Contentful Paint"),
        ("speed-index", "Speed Index"),
        ("interactive", "Time to Interactive"),
        ("total-blocking-time", "Total Blocking Time"),
        ("cumulative-layout-shift", "Cumulative Layout Shift"),
    ):
        audit = audits.get(audit_id) or {}
        metrics.append(
            LighthouseMetric(name=label, value=str(audit.get("displayValue") or ""), score=audit.get("score"))
        )

    page_load_ms = int((audits.get("interactive") or {}).get("numericValue") or 0)
    image_ms = int((audits.get("uses-optimized-images") or {}).get("numericValue") or 0)
    video_ms = int((audits.get("video-formats") or {}).get("numericValue") or 0)
    return LighthouseResult(
        checked=True,
        url=url,
        provider=provider,
        performance_score=_category_score(categories, "performance"),
        accessibility_score=_category_score(categories, "accessibility"),
        best_practices_score=_category_score(categories, "best-practices"),
        seo_score=_category_score(categories, "seo"),
        metrics=metrics,
        image_rendering_ms=image_ms,
        video_rendering_ms=video_ms,
        page_load_ms=page_load_ms,
    )


def _category_score(categories: dict, name: str) -> int:
    value = (categories.get(name) or {}).get("score")
    if value is None:
        return 0
    return int(round(float(value) * 100))


def _lookup_rank(keyword: str, domain: str) -> int | None:
    from geo_optimizer.core.audit_serp import _search_google

    results = _search_google(keyword)
    for item in results:
        if _domain_from_url(item.get("url", "")) == domain:
            return int(item.get("rank") or 0) or None
    return None


def _extract_domain_terms(text: str) -> list[str]:
    words = [word.lower() for word in text.split() if len(word) >= 4 and word.isalpha()]
    stop = {"with", "from", "that", "this", "your", "have", "will", "about", "more", "dans", "pour", "avec"}
    return [word for word, _ in Counter(word for word in words if word not in stop).most_common(20)]


def _estimate_authority(domain: str, soup, word_count: int) -> int:
    digest = int(hashlib.sha256(domain.encode("utf-8")).hexdigest()[:8], 16)
    score = 15 + digest % 35
    if soup is not None:
        score += min(20, len(soup.find_all("script", type="application/ld+json")) * 4)
        score += min(15, len(soup.find_all("a", href=True)) // 8)
        score += min(15, word_count // 400)
    return max(0, min(100, score))


def _page_title(soup) -> str:
    title = soup.find("title") if soup else None
    return title.get_text(" ", strip=True) if title else ""


def _domain_from_url(url: str) -> str:
    value = url if url.startswith(("http://", "https://")) else f"https://{url}"
    return (urlparse(value).hostname or url).lower().replace("www.", "")


def _clean_search_result_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in (parsed.hostname or ""):
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return unquote(values[0])
    return href


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

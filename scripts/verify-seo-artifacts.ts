/**
 * CI-friendly check: required SEO program files exist, JSON parses, minimal schema.
 * Run from repo root: npm run seo:verify
 */
import { existsSync, readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const REQUIRED_FILES = [
  "seo/CHANGELOG.md",
  "seo/README.md",
  "seo/audit-issues.json",
  "seo/representative-urls.json",
  "seo/decision-cards.md",
  "seo/gsc-dashboard-handbook.md",
  "seo/BACKLOG.md",
  "seo/PR_TEMPLATE.md",
] as const;

type AuditIssue = {
  id: string;
  priority: string;
  title: string;
  evidence: string;
  rollback: string;
  geo_scaled_content_risk: "low" | "medium" | "high" | string;
};

type AuditIssuesFile = {
  version: number;
  issues: AuditIssue[];
};

type RepresentativeUrlsFile = {
  version: number;
  locales: Record<string, string[]>;
  notes?: string;
};

function die(msg: string): never {
  console.error(`seo:verify — ${msg}`);
  process.exit(1);
}

function readText(rel: string): string {
  const p = join(ROOT, rel);
  if (!existsSync(p)) die(`missing file: ${rel}`);
  return readFileSync(p, "utf8");
}

function expectHeading(md: string, rel: string, needle: string): void {
  if (!md.includes(needle)) die(`${rel} must contain heading or marker: ${needle}`);
}

function main(): void {
  for (const rel of REQUIRED_FILES) {
    const p = join(ROOT, rel);
    if (!existsSync(p)) die(`missing: ${rel}`);
    const raw = readFileSync(p, "utf8");
    if (raw.trim().length < 80) die(`${rel} is too short (expected substantive content)`);
  }

  const changelog = readText("seo/CHANGELOG.md");
  expectHeading(changelog, "seo/CHANGELOG.md", "##");

  let audit: AuditIssuesFile;
  try {
    audit = JSON.parse(readText("seo/audit-issues.json")) as AuditIssuesFile;
  } catch {
    die("seo/audit-issues.json is not valid JSON");
  }
  if (typeof audit.version !== "number") die("audit-issues.json: missing numeric version");
  if (!Array.isArray(audit.issues)) die("audit-issues.json: issues must be an array");
  for (const issue of audit.issues) {
    for (const k of ["id", "priority", "title", "evidence", "rollback", "geo_scaled_content_risk"] as const) {
      if (typeof issue[k] !== "string" || !(issue[k] as string).trim()) {
        die(`audit-issues.json: issue ${issue.id ?? "?"} missing or empty field: ${k}`);
      }
    }
  }

  let urls: RepresentativeUrlsFile;
  try {
    urls = JSON.parse(readText("seo/representative-urls.json")) as RepresentativeUrlsFile;
  } catch {
    die("seo/representative-urls.json is not valid JSON");
  }
  if (typeof urls.version !== "number") die("representative-urls.json: missing numeric version");
  if (!urls.locales || typeof urls.locales !== "object") die("representative-urls.json: missing locales");
  for (const loc of ["en", "fr"] as const) {
    const arr = urls.locales[loc];
    if (!Array.isArray(arr) || arr.length === 0 || !arr.every((u) => typeof u === "string" && u.startsWith("http"))) {
      die(`representative-urls.json: locales.${loc} must be a non-empty array of http(s) URL strings`);
    }
  }

  expectHeading(readText("seo/decision-cards.md"), "seo/decision-cards.md", "2026-08-01");
  expectHeading(readText("seo/gsc-dashboard-handbook.md"), "seo/gsc-dashboard-handbook.md", "GSC");
  expectHeading(readText("seo/BACKLOG.md"), "seo/BACKLOG.md", "Backlog");
  expectHeading(readText("seo/PR_TEMPLATE.md"), "seo/PR_TEMPLATE.md", "##");
  expectHeading(readText("seo/README.md"), "seo/README.md", "seo/");

  console.log("seo:verify — OK (all artifacts present and structurally valid)");
}

main();

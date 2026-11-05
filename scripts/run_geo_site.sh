#!/usr/bin/env bash
set -u

usage() {
  echo "Usage: $0 <domain_url> [site_name] [site_desc] [output_dir]"
  echo "Example: $0 https://example.com \"Example\" \"Example site for AI engines\" out/example-com"
}

if [[ "${1:-}" == "" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

DOMAIN_URL="$1"
SITE_NAME="${2:-Site}"
SITE_DESC="${3:-Site map for AI engines}"
OUTPUT_DIR="${4:-out/$(echo "$DOMAIN_URL" | sed 's#https\\?://##; s#[^a-zA-Z0-9._-]#-#g')}"

mkdir -p "$OUTPUT_DIR"

if [[ -z "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="src"
fi

DOMAIN_HOST="$(python3 - <<'PY' "$DOMAIN_URL"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
print((u.hostname or "").strip())
PY
)"

SITEMAP_URL="https://www.${DOMAIN_HOST}/sitemap.xml"
if [[ "$DOMAIN_HOST" == www.* ]]; then
  SITEMAP_URL="https://${DOMAIN_HOST}/sitemap.xml"
fi

SAMPLE_LOG_FILE="${OUTPUT_DIR}/sample-access.log"
cat > "$SAMPLE_LOG_FILE" <<'EOF'
66.249.66.1 - - [29/Apr/2026:00:00:00 +0000] "GET / HTTP/1.1" 200 1234 "-" "Googlebot/2.1"
EOF

NAMES=(
  "audit"
  "fix"
  "llms"
  "schema"
  "diff"
  "coherence"
  "monitor"
  "track"
  "history"
  "logs"
  "snapshots"
)

run_geo_cmd() {
  local name="$1"
  case "$name" in
    audit) python3 -m geo_optimizer.cli.main audit --url "$DOMAIN_URL" --format json ;;
    fix) python3 -m geo_optimizer.cli.main fix --url "$DOMAIN_URL" ;;
    llms) python3 -m geo_optimizer.cli.main llms --base-url "$DOMAIN_URL" --site-name "$SITE_NAME" --description "$SITE_DESC" --output "$OUTPUT_DIR/llms.txt" ;;
    schema) python3 -m geo_optimizer.cli.main schema --type website --url "$DOMAIN_URL" ;;
    diff) python3 -m geo_optimizer.cli.main diff --before "$DOMAIN_URL" --after "$DOMAIN_URL" --format json ;;
    coherence) python3 -m geo_optimizer.cli.main coherence --sitemap "$SITEMAP_URL" --format json ;;
    monitor) python3 -m geo_optimizer.cli.main monitor --domain "$DOMAIN_HOST" --format json ;;
    track) python3 -m geo_optimizer.cli.main track --url "$DOMAIN_URL" --format json ;;
    history) python3 -m geo_optimizer.cli.main history --url "$DOMAIN_URL" --format json ;;
    logs) python3 -m geo_optimizer.cli.main logs --file "$SAMPLE_LOG_FILE" --format json ;;
    snapshots) python3 -m geo_optimizer.cli.main snapshots --query "$DOMAIN_HOST" --limit 5 --format json ;;
    *) return 127 ;;
  esac
}

summary_tmp="${OUTPUT_DIR}/summary.tmp.jsonl"
rm -f "$summary_tmp"

echo "============================================================"
echo " GEO RUNBOOK"
echo " Domain: $DOMAIN_URL"
echo " Output: $OUTPUT_DIR"
echo "============================================================"

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  stdout_file="${OUTPUT_DIR}/${name}.stdout.txt"
  stderr_file="${OUTPUT_DIR}/${name}.stderr.txt"
  output_file="${OUTPUT_DIR}/${name}.json"

  echo "==> Running: $name"
  run_geo_cmd "$name" >"$stdout_file" 2>"$stderr_file"
  exit_code=$?

  if [[ -s "$stdout_file" ]]; then
    cp "$stdout_file" "$output_file"
  else
    : > "$output_file"
  fi

  highlight="$(python3 - <<'PY' "$stdout_file" "$stderr_file"
import sys
from pathlib import Path
so = Path(sys.argv[1]).read_text(errors="ignore").strip().splitlines()
se = Path(sys.argv[2]).read_text(errors="ignore").strip().splitlines()
line = ""
if so:
    line = so[0][:220]
elif se:
    line = se[0][:220]
print(line.replace('"', "'"))
PY
)"

  python3 - <<'PY' "$summary_tmp" "$name" "$exit_code" "$output_file" "$highlight"
import json, sys
path, name, code, out, hl = sys.argv[1:]
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "name": name,
        "exit_code": int(code),
        "output_file": out,
        "highlights": [hl] if hl else [],
    }, ensure_ascii=False) + "\n")
PY
done

python3 - <<'PY' "$summary_tmp" "$OUTPUT_DIR/summary.json" "$OUTPUT_DIR/report.md" "$DOMAIN_URL"
import json, sys
from datetime import datetime, timezone
from pathlib import Path

tmp, out, report, domain = sys.argv[1:]
cmds = []
with open(tmp, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            cmds.append(json.loads(line))

failed = [c for c in cmds if c["exit_code"] != 0]
summary = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "domain": domain,
    "commands": cmds,
    "top_issues": [f"{c['name']} failed with exit {c['exit_code']}" for c in failed][:5],
    "top_actions": [
        "Review out/coherence.json for title/semantic collisions",
        "Review out/audit.json recommendations and prioritize P1 fixes",
        "Publish llms.txt if generated and re-run audit",
    ],
    "ready_for_publish": len(failed) == 0,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

status_icon = lambda c: "✅" if c["exit_code"] == 0 else "❌"
lines = []
lines.append("# GEO Site Run Report")
lines.append("")
lines.append(f"- **Domain:** `{domain}`")
lines.append(f"- **Generated:** `{summary['generated_at']}`")
lines.append(f"- **Ready for publish:** `{'yes' if summary['ready_for_publish'] else 'no'}`")
lines.append("")
lines.append("## Command Status")
lines.append("")
lines.append("| Status | Command | Exit | Output | Highlight |")
lines.append("|---|---|---:|---|---|")
for c in cmds:
    hl = (c.get("highlights") or [""])[0].replace("|", "\\|")
    lines.append(
        f"| {status_icon(c)} | `{c['name']}` | `{c['exit_code']}` | `{c['output_file']}` | {hl} |"
    )

lines.append("")
lines.append("## Top Issues")
lines.append("")
if summary["top_issues"]:
    for issue in summary["top_issues"]:
        lines.append(f"- {issue}")
else:
    lines.append("- None")

lines.append("")
lines.append("## Top Actions")
lines.append("")
for action in summary["top_actions"]:
    lines.append(f"- {action}")

Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")

print("")
print("============================================================")
print(" GEO RUN SUMMARY")
print("============================================================")
for c in cmds:
    print(f"{status_icon(c)} {c['name']:<10} exit={c['exit_code']}  output={c['output_file']}")
print("------------------------------------------------------------")
print(f"Ready for publish: {'yes' if summary['ready_for_publish'] else 'no'}")
print(f"JSON summary     : {out}")
print(f"Markdown report  : {report}")
print("============================================================")
PY

rm -f "$summary_tmp"

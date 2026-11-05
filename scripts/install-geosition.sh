#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${GEOSITION_HOME:-${HOME}/.geosition}"
APP_DIR="${APP_HOME}/app"
VENV_DIR="${APP_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"
WRAPPER="${BIN_DIR}/geosition"
INSTALL_SOURCE="${GEOSITION_INSTALL_SOURCE:-geosition[web]}"

log() {
  printf '▮▮▮▮ %s\n' "$1"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

need_cmd python3

log "Creating GEOSITION app directory..."
mkdir -p "${APP_DIR}" "${BIN_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  log "Creating isolated Python environment..."
  python3 -m venv "${VENV_DIR}"
fi

log "Installing GEOSITION..."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null
"${VENV_DIR}/bin/python" -m pip install --upgrade "${INSTALL_SOURCE}"

log "Installing geosition command..."
cat >"${WRAPPER}" <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/geosition" "\$@"
EOF
chmod +x "${WRAPPER}"

PROFILE=""
if [[ -n "${ZSH_VERSION:-}" || "${SHELL:-}" == */zsh ]]; then
  PROFILE="${HOME}/.zshrc"
elif [[ -n "${BASH_VERSION:-}" || "${SHELL:-}" == */bash ]]; then
  PROFILE="${HOME}/.bashrc"
fi

if [[ -n "${PROFILE}" ]]; then
  touch "${PROFILE}"
  if ! grep -F "${BIN_DIR}" "${PROFILE}" >/dev/null 2>&1; then
    printf '\n# GEOSITION CLI\nexport PATH="%s:$PATH"\n' "${BIN_DIR}" >>"${PROFILE}"
    PATH_NOTE="Added ${BIN_DIR} to PATH in ${PROFILE}"
  else
    PATH_NOTE="${BIN_DIR} already present in ${PROFILE}"
  fi
else
  PATH_NOTE="Add ${BIN_DIR} to PATH if geosition is not found"
fi

cat <<EOF

╭────────────────────────────────────────────╮
│ GEOSITION installed successfully           │
╰────────────────────────────────────────────╯

App installed to ${APP_DIR}
Command installed to ${WRAPPER}
${PATH_NOTE}

Try:
  geosition init
  geosition start
  # open /platform, enter your domain, create account, verify DNS TXT
  geosition worker start --once --answers-file answers.json

Hosted queue worker:
  export GEOSITION_PLATFORM_URL="https://geositionai.com"
  export GEOSITION_WORKER_TOKEN="your-vercel-worker-token"
  geosition worker start --once

That worker drains queued sitemap page audits and hosted collection jobs.
Weekly snapshots can also ingest crawler-log evidence through /api/v1/index/crawler-log
and persist page scores in geo_page_audits once the Supabase migration is applied.

You may need to restart your terminal first.
EOF

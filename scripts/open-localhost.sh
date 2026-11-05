#!/usr/bin/env bash
set -euo pipefail

PORT_ARG="${1:-8001}"
PATH_WITH_HASH="${2:-/platform}"
HOST="${HOST:-127.0.0.1}"

if [[ "${PORT_ARG}" == */* ]]; then
  PORT="${PORT_ARG%%/*}"
  PATH_WITH_HASH="/${PORT_ARG#*/}"
else
  PORT="${PORT_ARG}"
fi

URL="http://${HOST}:${PORT}${PATH_WITH_HASH}"
LOG_FILE="/tmp/geo-optimizer-${PORT}.log"

if [[ ! "$PATH_WITH_HASH" =~ ^/ ]]; then
  PATH_WITH_HASH="/${PATH_WITH_HASH}"
  URL="http://${HOST}:${PORT}${PATH_WITH_HASH}"
fi

echo "Opening ${URL}"

if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${PIDS}" ]]; then
    echo "Killing stale listener(s) on ${PORT}: ${PIDS}"
    kill ${PIDS} 2>/dev/null || true
    sleep 0.6
  fi
fi

export PYTHONPATH="${PYTHONPATH:-src}"
python3 -m geo_optimizer.web.cli --host "${HOST}" --port "${PORT}" >"${LOG_FILE}" 2>&1 &
SERVER_PID="$!"

cleanup_failed_start() {
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "Server failed to start. Log:"
    tail -80 "${LOG_FILE}" || true
    exit 1
  fi
}

for _ in {1..60}; do
  cleanup_failed_start
  if curl -fsS "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
  echo "Server did not become ready. Log:"
  tail -80 "${LOG_FILE}" || true
  exit 1
fi

STATUS="$(curl -sS -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}${PATH_WITH_HASH%%#*}" || true)"
if [[ "${STATUS}" == "404" ]]; then
  echo "Server is running, but ${PATH_WITH_HASH%%#*} is not a route in this app."
  echo "Try: scripts/open-localhost.sh ${PORT} /platform"
  exit 1
fi

open "${URL}"
echo "Ready: ${URL}"
echo "Server PID: ${SERVER_PID}"
echo "Log: ${LOG_FILE}"
echo "Server is running. Press Ctrl+C in this terminal to stop it."
wait "${SERVER_PID}"

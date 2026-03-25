#!/usr/bin/env bash
# Startet LiteLLM (Docker), Key-Portal und zwei Cloudflare-Tunnel.
# Läuft solange bis Ctrl-C gedrückt wird – alle Prozesse werden dann beendet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORTAL_DIR="$SCRIPT_DIR/../hsog-litellm-key-portal"

# ── PIDs initialisieren ───────────────────────────────
PORTAL_PID=""
CF_LITELLM_PID=""
CF_PORTAL_PID=""

# ── Voraussetzungen prüfen ────────────────────────────
for cmd in docker cloudflared uv; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "FEHLER: '$cmd' nicht gefunden. Bitte installieren." >&2
    exit 1
  fi
done

# ── Aufräumen beim Beenden ────────────────────────────
cleanup() {
  echo ""
  echo "Beende alle Prozesse..."
  [ -n "$PORTAL_PID" ]    && kill "$PORTAL_PID"    2>/dev/null || true
  [ -n "$CF_LITELLM_PID" ] && kill "$CF_LITELLM_PID" 2>/dev/null || true
  [ -n "$CF_PORTAL_PID" ]  && kill "$CF_PORTAL_PID"  2>/dev/null || true
  docker compose --project-directory "$SCRIPT_DIR" down
  docker compose --project-directory "$PORTAL_DIR" down
}
trap cleanup EXIT INT TERM

# ── LiteLLM starten ──────────────────────────────────
echo "Starte LiteLLM (Docker)..."
docker compose --project-directory "$SCRIPT_DIR" up -d

# ── Portal-Datenbank starten ─────────────────────────
echo "Starte Key-Portal Datenbank (Docker)..."
docker compose --project-directory "$PORTAL_DIR" up -d

# ── Auf LiteLLM warten ───────────────────────────────
echo "Warte auf LiteLLM (Port 4000)..."
for i in $(seq 1 60); do
  if nc -z localhost 4000 &>/dev/null; then
    echo "LiteLLM bereit."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "WARNUNG: LiteLLM antwortet nicht nach 120s, fahre trotzdem fort." >&2
  fi
  sleep 2
done

echo "Warte auf Portal-Datenbank (Port 5433)..."
for i in $(seq 1 30); do
  if nc -z localhost 5433 &>/dev/null; then
    echo "Portal-DB bereit."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNUNG: Portal-DB antwortet nicht nach 60s, fahre trotzdem fort." >&2
  fi
  sleep 2
done

# ── Key-Portal starten ───────────────────────────────
echo "Starte Key-Portal..."
(cd "$PORTAL_DIR" && uv run portal.py) &
PORTAL_PID=$!
sleep 3

# ── Cloudflare-Tunnel starten ────────────────────────
echo "Starte Cloudflare-Tunnel für LiteLLM..."
cloudflared tunnel --url http://localhost:4000 --no-autoupdate 2>&1 \
  | grep --line-buffered -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
  | head -1 \
  | xargs -I{} echo "  LiteLLM-URL:  {}" &
CF_LITELLM_PID=$!

echo "Starte Cloudflare-Tunnel für Key-Portal..."
cloudflared tunnel --url http://localhost:8080 --no-autoupdate 2>&1 \
  | grep --line-buffered -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
  | head -1 \
  | xargs -I{} echo "  Portal-URL:   {}" &
CF_PORTAL_PID=$!

echo ""
echo "Alle Dienste gestartet. URLs erscheinen in Kürze oben."
echo "Ctrl-C zum Beenden."
echo ""

wait

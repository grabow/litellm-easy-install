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

# ── Cloudflare-Tunnel starten (benannte Tunnel mit festen URLs) ──
LITELLM_TOKEN_FILE="$HOME/.cloudflared/hsog-litellm.token"
PORTAL_TOKEN_FILE="$HOME/.cloudflared/hsog-portal.token"

if [ ! -f "$LITELLM_TOKEN_FILE" ] || [ ! -f "$PORTAL_TOKEN_FILE" ]; then
  echo "FEHLER: Tunnel-Token-Dateien nicht gefunden unter ~/.cloudflared/" >&2
  exit 1
fi

LITELLM_TOKEN=$(cat "$LITELLM_TOKEN_FILE")
PORTAL_TOKEN=$(cat "$PORTAL_TOKEN_FILE")

echo "Starte Cloudflare-Tunnel für LiteLLM..."
cloudflared tunnel --no-autoupdate run \
  --token "$LITELLM_TOKEN" \
  --url http://localhost:4000 &
CF_LITELLM_PID=$!

echo "Starte Cloudflare-Tunnel für Key-Portal..."
cloudflared tunnel --no-autoupdate run \
  --token "$PORTAL_TOKEN" \
  --url http://localhost:8080 &
CF_PORTAL_PID=$!

# Feste URLs ausgeben
echo ""
echo "  LiteLLM-URL:  https://a4465488-cbfb-4083-a0cf-b918043aa49a.cfargotunnel.com"
echo "  Portal-URL:   https://8dc995b2-f8bb-4e3a-94da-1ca2abbd6004.cfargotunnel.com"
echo ""
echo "Alle Dienste gestartet. Ctrl-C zum Beenden."
echo ""

wait

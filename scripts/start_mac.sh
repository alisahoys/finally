#!/usr/bin/env bash
# Run FinAlly in Docker on macOS, Linux or WSL. Safe to run repeatedly.
#   --build      rebuild the image and replace the running container
#   --simulator  use the simulator even if .env has a MASSIVE_API_KEY
#   --open       open the browser once the app is healthy
# FINALLY_NAME and FINALLY_PORT run a second copy alongside the default one.
set -e
cd "$(dirname "$0")/.."

NAME="${FINALLY_NAME:-finally}"
PORT="${FINALLY_PORT:-8000}"
URL="http://localhost:$PORT"
HEALTH_TRIES=30
build=false replace=false open=false
simulator=()

for arg in "$@"; do
  case "$arg" in
    --build) build=true replace=true ;;
    --simulator) simulator=(-e MASSIVE_API_KEY=) replace=true ;;
    --open) open=true ;;
    *) echo "Usage: $0 [--build] [--simulator] [--open]" >&2; exit 1 ;;
  esac
done

open_browser() {
  for opener in open wslview xdg-open; do
    command -v "$opener" >/dev/null && { "$opener" "$URL"; return; }
  done
  command -v cmd.exe >/dev/null && cmd.exe /c start "" "$URL" 2>/dev/null
}

wait_for_health() {
  for ((try = 0; try < HEALTH_TRIES; try++)); do
    curl -fsS "$URL/api/health" >/dev/null 2>&1 && return
    sleep 1
  done
  echo "Health check failed at $URL/api/health. Recent logs:" >&2
  docker logs --tail 20 "$NAME" >&2
  exit 1
}

market_source() {
  if [ -n "$(docker exec "$NAME" printenv MASSIVE_API_KEY || true)" ]; then
    echo "Massive API"
  else
    echo "simulator"
  fi
}

if [ ! -f .env ]; then
  echo "No .env file found. Run: cp .env.example .env" >&2
  exit 1
fi

if [ -n "$(docker ps -q -f "name=^/$NAME$")" ] && [ "$replace" = false ]; then
  echo "$NAME is already running."
else
  if [ "$build" = true ] || ! docker image inspect "$NAME" >/dev/null 2>&1; then
    docker build -t "$NAME" .
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -v "$NAME-data:/app/db" -p "$PORT:8000" \
    --env-file .env "${simulator[@]}" "$NAME" >/dev/null
fi

wait_for_health
echo "FinAlly is running at $URL (market data: $(market_source))"
if [ "$open" = true ]; then open_browser; fi

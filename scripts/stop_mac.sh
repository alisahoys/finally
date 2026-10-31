#!/usr/bin/env bash
# Stop and remove the FinAlly container. The data volume is kept. Safe to run repeatedly.
set -e
NAME="${FINALLY_NAME:-finally}"
docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "$NAME stopped. Data is kept in the $NAME-data volume."

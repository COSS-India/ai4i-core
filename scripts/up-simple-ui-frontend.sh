#!/usr/bin/env bash
# Drop a leftover ai4v-simple-ui container (fixes "name already in use"), then start the service.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCKER=(docker)
if ! docker info &>/dev/null; then
  if sudo -n true 2>/dev/null; then
    DOCKER=(sudo docker)
  else
    echo "Docker is not reachable. Use: sudo usermod -aG docker \"\$USER\" (then re-login), or run:" >&2
    echo "  sudo $0" >&2
    exit 1
  fi
fi

"${DOCKER[@]}" rm -f ai4v-simple-ui 2>/dev/null || true
exec "${DOCKER[@]}" compose up -d simple-ui-frontend

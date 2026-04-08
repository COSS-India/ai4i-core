#!/usr/bin/env bash
# Replace only the simple-ui container on the existing compose network.
# Use when `docker compose up -d simple-ui-frontend` fails with
# "network ... has active endpoints" (partial stack reconcile).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
if [[ -f .env ]]; then set -a && source .env && set +a; fi
PROJECT="${COMPOSE_PROJECT_NAME:-ai4i-orchestrate}"
NET="${PROJECT}_microservices-network"
IMAGE="${PROJECT}-simple-ui-frontend:latest"

docker stop ai4v-simple-ui 2>/dev/null || true
docker rm ai4v-simple-ui 2>/dev/null || true

docker run -d \
  --name ai4v-simple-ui \
  --restart unless-stopped \
  --network "$NET" \
  -p 3000:3000 \
  -e HOSTNAME=0.0.0.0 \
  -e "NEXT_PUBLIC_API_URL=${SIMPLE_UI_NEXT_PUBLIC_API_URL:-http://localhost:8080}" \
  -e "NEXT_PUBLIC_TELEMETRY_SERVICE_URL=${SIMPLE_UI_NEXT_PUBLIC_TELEMETRY_SERVICE_URL:-http://localhost:8084}" \
  -e "NEXT_PUBLIC_ASR_STREAM_URL=${SIMPLE_UI_NEXT_PUBLIC_ASR_STREAM_URL:-ws://localhost:8087/socket.io/asr}" \
  -e "NEXT_PUBLIC_TTS_STREAM_URL=${SIMPLE_UI_NEXT_PUBLIC_TTS_STREAM_URL:-ws://localhost:8088/socket.io/tts}" \
  "$IMAGE"

echo "Started ai4v-simple-ui on network $NET (image $IMAGE). Open http://localhost:3000"

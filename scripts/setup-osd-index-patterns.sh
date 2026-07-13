#!/usr/bin/env bash
#
# setup-osd-index-patterns.sh — Create the OpenSearch Dashboards index patterns
# ("traces-*", "logs-*") that Step 4.3 of SETUP_DOCUMENT_PPU.md used to create
# by hand.
#
# Nothing in OpenSearch Dashboards is browsable until these exist. This only
# needs `opensearch-dashboards` up (traces don't need to be flowing yet), so
# this polls until it's reachable rather than requiring the caller to time it.
#
# Usage:
#   ./scripts/setup-osd-index-patterns.sh
#
# Safe to re-run — a 409 (pattern already exists) is treated as success.
#
set -euo pipefail

OSD_URL="${OSD_URL:-http://localhost:5602}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-120}"

echo "Waiting for OpenSearch Dashboards at ${OSD_URL} ..."
elapsed=0
until curl -sf -o /dev/null "${OSD_URL}/api/status"; do
    if [ "$elapsed" -ge "$MAX_WAIT_SECONDS" ]; then
        echo "ERROR: OpenSearch Dashboards not reachable after ${MAX_WAIT_SECONDS}s" >&2
        exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done
echo "  OpenSearch Dashboards is up."

create_index_pattern() {
    local id="$1"
    local title="$2"
    local http_code

    http_code=$(curl -s -o /tmp/osd-index-pattern-response.json -w "%{http_code}" \
        -X POST "${OSD_URL}/api/saved_objects/index-pattern/${id}" \
        -H "osd-xsrf: true" -H "Content-Type: application/json" \
        -d "{\"attributes\":{\"title\":\"${title}\",\"timeFieldName\":\"@timestamp\"}}")

    if [ "$http_code" = "200" ] || [ "$http_code" = "409" ]; then
        echo "  OK    ${title} (HTTP ${http_code})"
    else
        echo "  FAIL  ${title} (HTTP ${http_code}): $(cat /tmp/osd-index-pattern-response.json)" >&2
        return 1
    fi
}

create_index_pattern "traces-star" "traces-*"
create_index_pattern "logs-star" "logs-*"

echo "Done — index patterns ready."

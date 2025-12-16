#!/usr/bin/env bash

# Generate an OpenAPI document for Kong-facing Swagger UI
# by fetching the API Gateway's OpenAPI and rewriting:
#   - servers URL → Kong URL
#   - security schemes → bearer + x-api-key
#
# Usage:
#   ./scripts/generate-kong-openapi.sh [api_gateway_base_url] [kong_base_url]
# Example:
#   ./scripts/generate-kong-openapi.sh http://localhost:8080 http://localhost:8000

set -euo pipefail

API_GATEWAY_URL="${1:-http://localhost:8080}"
KONG_URL="${2:-http://localhost:8000}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/docs"
OUTPUT_FILE="${OUTPUT_DIR}/kong-openapi.json"

mkdir -p "${OUTPUT_DIR}"

echo "Fetching OpenAPI from API Gateway: ${API_GATEWAY_URL}/openapi.json"

TMP_FILE="$(mktemp)"
curl -fsSL "${API_GATEWAY_URL}/openapi.json" > "${TMP_FILE}"

echo "Rewriting servers and security to target Kong: ${KONG_URL}"

python3 - "$TMP_FILE" "$KONG_URL" "$OUTPUT_FILE" << 'PYCODE'
import json
import sys
from pathlib import Path
import os
from urllib import request as urlrequest, error as urlerror

if len(sys.argv) != 4:
    print("Usage: script <input_json> <kong_url> <output_json>", file=sys.stderr)
    sys.exit(1)

input_path = Path(sys.argv[1])
kong_url = sys.argv[2]
output_path = Path(sys.argv[3])

with input_path.open("r", encoding="utf-8") as f:
    spec = json.load(f)

# 1) Point Swagger "Try it out" requests to Kong instead of the API gateway
spec["servers"] = [
    {
        "url": kong_url,
        "description": "Kong API Gateway"
    }
]

# 2) Normalize security schemes so we only expose two in Swagger
#    and remove confusing internal headers like x-auth-source.
components = spec.setdefault("components", {})
security_schemes = components.setdefault("securitySchemes", {})

# Remove any duplicate / legacy schemes we don't want to expose
for key in list(security_schemes.keys()):
    if key not in ("HTTPBearer", "APIKeyHeader"):
        security_schemes.pop(key, None)

# Ensure HTTPBearer exists
security_schemes.setdefault(
    "HTTPBearer",
    {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    },
)

# Ensure APIKeyHeader exists
security_schemes.setdefault(
    "APIKeyHeader",
    {
        "type": "apiKey",
        "in": "header",
        "name": "x-api-key",
    },
)

# 3) Apply both security schemes globally
spec["security"] = [
    {"HTTPBearer": []},
    {"APIKeyHeader": []},
]

# 4) Remove x-auth-source parameter from components and operations
params = components.setdefault("parameters", {})
params.pop("XAuthSource", None)

paths = spec.get("paths", {})
for path_item in paths.values():
    if not isinstance(path_item, dict):
        continue
    for op in path_item.values():
        if not isinstance(op, dict):
            continue
        if "parameters" not in op:
            continue
        filtered = []
        for p in op["parameters"]:
            # $ref to XAuthSource
            if isinstance(p, dict) and "$ref" in p:
                ref = p["$ref"]
                if ref.endswith("/parameters/XAuthSource"):
                    continue
            # inline x-auth-source header
            if isinstance(p, dict) and p.get("in") == "header" and str(p.get("name", "")).lower() == "x-auth-source":
                continue
            filtered.append(p)
        op["parameters"] = filtered

# 5) Hide NMT endpoints that are not implemented in the backend from Swagger
for nmt_path in [
    "/api/v1/nmt/models",
    "/api/v1/nmt/services",
    "/api/v1/nmt/languages",
    "/api/v1/nmt/batch-translate",
]:
    paths.pop(nmt_path, None)

# 6) Merge LLM service OpenAPI (if available) so LLM endpoints appear in Swagger
llm_openapi_url = os.getenv("LLM_OPENAPI_URL", "http://localhost:8093/openapi.json")
try:
    resp = urlrequest.urlopen(llm_openapi_url, timeout=5)
    llm_spec = json.load(resp)
except Exception as e:
    llm_spec = None

if llm_spec:
    llm_components = llm_spec.get("components", {})
    # Merge component subsets commonly used by LLM spec
    for key in ["schemas", "parameters", "requestBodies", "responses"]:
        src = llm_components.get(key, {})
        if not src:
            continue
        dst = components.setdefault(key, {})
        for name, value in src.items():
            if name not in dst:
                dst[name] = value

    llm_paths = llm_spec.get("paths", {})
    for path, item in llm_paths.items():
        # Only include LLM routes
        if not str(path).startswith("/api/v1/llm"):
            continue

        # Remove explicit auth header parameters; we rely on global security instead
        if isinstance(item, dict):
            for method_def in item.values():
                if not isinstance(method_def, dict):
                    continue
                if "parameters" not in method_def:
                    continue
                filtered_params = []
                for p in method_def["parameters"]:
                    if not isinstance(p, dict):
                        filtered_params.append(p)
                        continue
                    name = str(p.get("name", "")).lower()
                    location = p.get("in")
                    if location == "header" and name in ("authorization", "x-api-key", "x-auth-source"):
                        continue
                    filtered_params.append(p)
                method_def["parameters"] = filtered_params

        # Avoid overwriting if already present
        if path not in paths:
            paths[path] = item


with output_path.open("w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2)

print(f"Wrote Kong OpenAPI spec to: {output_path}", file=sys.stderr)
PYCODE

rm -f "${TMP_FILE}"

echo "Done. You can now point a Swagger UI instance at ${OUTPUT_FILE}"



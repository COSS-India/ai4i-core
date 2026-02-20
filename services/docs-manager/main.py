"""
Docs Manager: unified API documentation service.

Loads per-service OpenAPI specs from the registry (specs/service-docs-registry.yaml),
merges them into a single OpenAPI 3.0 document and serves Swagger UI. All specs
reflect APIs exposed via the API Gateway.

Endpoints:
  GET /openapi.json  – Merged OpenAPI 3.0 spec
  GET /docs          – Swagger UI
  GET /specs/{service_name}/openapi.json – Per-service spec
  GET /health        – Health check
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

app = FastAPI(
    title="API Documentation",
    version="1.0.0",
    description="Unified API documentation for all public microservice APIs (as exposed via API Gateway).",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_here = Path(__file__).resolve().parent
_specs_dir = _here / "specs"
REGISTRY_ENV = "SERVICE_DOCS_REGISTRY_PATH"
GATEWAY_URL_ENV = "API_GATEWAY_URL"
USE_API_PROXY_ENV = "USE_API_PROXY"
DEFAULT_GATEWAY_URL = "http://localhost:8080"
DEFAULT_REGISTRY = _specs_dir / "service-docs-registry.yaml"
SPECS_ROOT_ENV = "SPECS_ROOT"


def _registry_path() -> Path:
    path = os.getenv(REGISTRY_ENV)
    if path:
        return Path(path)
    return DEFAULT_REGISTRY


def _specs_root_path() -> Path:
    """Directory used to resolve spec_file paths from the registry."""
    root = os.getenv(SPECS_ROOT_ENV)
    if root:
        return Path(root)
    return _specs_dir


def _gateway_url() -> str | None:
    """API_GATEWAY_URL from environment, or None to use registry default."""
    val = os.getenv(GATEWAY_URL_ENV)
    return val.rstrip("/") if val else None


def _gateway_base_url() -> str:
    """Base URL for the API Gateway used by the proxy."""
    registry = _load_registry()
    return (_gateway_url() or registry.get("api_gateway_url") or DEFAULT_GATEWAY_URL).rstrip("/")


def _use_api_proxy() -> bool:
    """True if Swagger UI should use /api-proxy (same-origin proxy). False when deployed
    behind a gateway (e.g. APISIX) with no /api-proxy route — then Try it out calls API_GATEWAY_URL directly."""
    val = os.getenv(USE_API_PROXY_ENV, "true").strip().lower()
    return val in ("true", "1", "yes")


def _openapi_server_url() -> str:
    """Server URL shown in OpenAPI spec (for Try it out)."""
    if _use_api_proxy():
        return "/api-proxy"
    return _gateway_base_url()


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"api_gateway_url": _gateway_url() or DEFAULT_GATEWAY_URL, "services": {}}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {"services": {}}


def _load_spec_file(rel_path: str) -> dict[str, Any] | None:
    """Load one OpenAPI spec (YAML or JSON) by path relative to specs root."""
    root = _specs_root_path()
    path = (root / rel_path).resolve()
    if not path.exists():
        return None
    with open(path, "r") as f:
        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(f)
        if path.suffix == ".json":
            return json.load(f)
    return None


def _merge_schemas(
    base: dict[str, Any],
    incoming: dict[str, Any],
    prefix: str,
) -> None:
    """Merge components/schemas from incoming into base with a prefix; rewrite $refs accordingly."""
    inc_schemas = (incoming.get("components") or {}).get("schemas") or {}
    if not inc_schemas:
        return
    base_components = base.setdefault("components", {})
    base_schemas = base_components.setdefault("schemas", {})
    for name, schema in inc_schemas.items():
        base_schemas[f"{prefix}_{name}"] = _rewrite_refs(schema, prefix, prefix)


def _merge_responses(
    base: dict[str, Any],
    incoming: dict[str, Any],
    prefix: str,
) -> None:
    """Merge components/responses from incoming into base with a prefix; rewrite $refs accordingly."""
    inc_resp = (incoming.get("components") or {}).get("responses") or {}
    if not inc_resp:
        return
    base_components = base.setdefault("components", {})
    base_resp = base_components.setdefault("responses", {})
    for name, resp in inc_resp.items():
        base_resp[f"{prefix}_{name}"] = _rewrite_refs(resp, prefix, prefix)


def _rewrite_refs(obj: Any, schema_prefix: str, response_prefix: str) -> Any:
    """Return a copy of obj with $ref values updated to use prefixed component names."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str):
                if v.startswith("#/components/schemas/"):
                    name = v.split("/")[-1]
                    out[k] = f"#/components/schemas/{schema_prefix}_{name}"
                elif v.startswith("#/components/responses/"):
                    name = v.split("/")[-1]
                    out[k] = f"#/components/responses/{response_prefix}_{name}"
                else:
                    out[k] = v
            else:
                out[k] = _rewrite_refs(v, schema_prefix, response_prefix)
        return out
    if isinstance(obj, list):
        return [_rewrite_refs(x, schema_prefix, response_prefix) for x in obj]
    return obj


def _apply_tag(op: dict[str, Any], tag: str) -> dict[str, Any]:
    """Set the operation's tags to the single registry tag for this service.
    Remove operation-level security so the merged doc's global security
    (BearerAuth + ApiKeyAuth) applies to every operation; otherwise Swagger UI
    would only send the auth method(s) listed per-operation (e.g. only Bearer).
    """
    op = dict(op)
    op["tags"] = [tag]
    op.pop("security", None)
    return op


def _merge_paths(
    base: dict[str, Any],
    incoming: dict[str, Any],
    tag: str,
    schema_prefix: str,
    response_prefix: str,
) -> None:
    """Merge paths from incoming into base; tag operations and rewrite $refs."""
    inc_paths = incoming.get("paths") or {}
    base_paths = base.setdefault("paths", {})
    methods = ("get", "post", "put", "patch", "delete", "head", "options")
    for path_key, path_item in inc_paths.items():
        if path_key not in base_paths:
            base_paths[path_key] = {}
        target = base_paths[path_key]
        path_item = _rewrite_refs(path_item, schema_prefix, response_prefix)
        for method in methods:
            op = path_item.get(method) if isinstance(path_item, dict) else None
            if isinstance(op, dict):
                target[method] = _apply_tag(op, tag)


def _tag_for_service(service_name: str, meta: dict[str, Any]) -> str:
    """Tag used for this service in the merged OpenAPI document."""
    tag = (meta.get("description") or service_name).strip()
    return tag or service_name.replace("-", " ").title()


def _add_service_spec(
    merged: dict[str, Any],
    service_name: str,
    meta: dict[str, Any],
    seen_tags: set[str],
) -> None:
    """Load and merge one service spec into the combined document."""
    spec_file = meta.get("spec_file")
    if not spec_file:
        return
    spec = _load_spec_file(spec_file)
    if not spec:
        return
    tag = _tag_for_service(service_name, meta)
    if tag not in seen_tags:
        seen_tags.add(tag)
        merged["tags"].append({"name": tag, "description": f"APIs for {tag}"})
    prefix = service_name.replace("-", "_")
    _merge_schemas(merged, spec, prefix)
    _merge_responses(merged, spec, prefix)
    _merge_paths(merged, spec, tag, prefix, prefix)


def _build_merged_spec() -> dict[str, Any]:
    """Build the merged OpenAPI 3.0 spec from the registry."""
    registry = _load_registry()
    services = registry.get("services") or {}

    merged: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": "AI4Inclusion APIs",
            "description": "A comprehensive microservices based platform to handle language based AI models inferences at scale.",
            "version": "1.0.0",
        },
        "servers": [
            {"url": _openapi_server_url(), "description": "API Gateway"}
        ],
        "paths": {},
        "components": {"schemas": {}, "responses": {}, "securitySchemes": {}},
        "tags": [],
        "security": [{"BearerAuth": []}, {"ApiKeyAuth": []}],
    }
    merged["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT or API Key",
        "description": "Bearer token in Authorization header (Bearer <token>)",
    }
    merged["components"]["securitySchemes"]["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key in X-API-Key header",
    }

    seen_tags: set[str] = set()
    for service_name, meta in services.items():
        _add_service_spec(merged, service_name, meta, seen_tags)

    if not merged["paths"]:
        merged["paths"]["/"] = {
            "get": {
                "tags": ["Status"],
                "summary": "Service status",
                "responses": {"200": {"description": "No service specifications registered."}},
            }
        }
        merged["tags"].insert(0, {"name": "Status", "description": "Service status"})

    return merged


_merged_spec: dict[str, Any] | None = None


def _get_merged_spec() -> dict[str, Any]:
    global _merged_spec
    if _merged_spec is None:
        _merged_spec = _build_merged_spec()
    return _merged_spec


_PROXY_SKIP_REQUEST_HEADERS = frozenset(
    {"connection", "host", "transfer-encoding", "keep-alive", "te", "trailer", "upgrade"}
)
_PROXY_SKIP_RESPONSE_HEADERS = frozenset(
    {"connection", "transfer-encoding", "keep-alive", "te", "trailer", "upgrade"}
)


@app.api_route("/api-proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def api_proxy(request: Request, path: str):
    """Proxy requests to the API Gateway for same-origin Try it out in Swagger UI."""
    base = _gateway_base_url()
    url = f"{base}/{path}" if path else base
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _PROXY_SKIP_REQUEST_HEADERS
    }
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                request.method,
                url,
                headers=headers,
                content=body if body else None,
            )
    except httpx.ConnectError as e:
        logger.warning("API Gateway unreachable at %s: %s", base, e)
        return JSONResponse(
            {"detail": "Upstream API Gateway is unavailable."},
            status_code=502,
        )
    response_headers = [
        (k, v) for k, v in resp.headers.items()
        if k.lower() not in _PROXY_SKIP_RESPONSE_HEADERS
    ]
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(response_headers),
    )


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "docs-manager"}


@app.get("/openapi.json")
def openapi_json():
    """Return the merged OpenAPI 3.0 spec for all registered services."""
    return JSONResponse(_get_merged_spec())


@app.get("/docs", response_class=HTMLResponse)
def swagger_ui():
    """Serve Swagger UI for the merged API documentation."""
    spec_url = "/openapi.json"
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>API Documentation</title>
  <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
  <style>
    .swagger-ui .topbar {{ display: none; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function() {{
      SwaggerUIBundle({{
        url: "{spec_url}",
        dom_id: '#swagger-ui',
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "StandaloneLayout",
        persistAuthorization: true
      }});
    }};
  </script>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/")
def index():
    """Service info and links to documentation."""
    return {
        "service": "docs-manager",
        "openapi": "/openapi.json",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/specs/{service_name}/openapi.json")
def service_openapi(service_name: str):
    """Return the OpenAPI spec for the given service."""
    registry = _load_registry()
    services = registry.get("services") or {}
    if service_name not in services:
        return JSONResponse({"detail": "Service not found."}, status_code=404)
    spec_file = services[service_name].get("spec_file")
    if not spec_file:
        return JSONResponse({"detail": "Spec not configured for this service."}, status_code=404)
    spec = _load_spec_file(spec_file)
    if not spec:
        return JSONResponse({"detail": "Spec file not found or unreadable."}, status_code=404)
    spec["servers"] = [{"url": _openapi_server_url(), "description": "API Gateway"}]
    return JSONResponse(spec)

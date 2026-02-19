"""
Docs Manager – single Swagger UI for all public APIs.

Loads one OpenAPI YAML/JSON per service from this service's specs/ folder (as listed in
specs/service-docs-registry.yaml). Merges them into one OpenAPI 3.0 spec and
serves a single Swagger UI. APIs are accurate to what is implemented in each
microservice and exposed via the API Gateway.

- GET /openapi.json  – merged OpenAPI spec (server URL = API Gateway for Try it out)
- GET /docs          – Swagger UI (single document)
- GET /specs/{service_name}/openapi.json – per-service spec (optional)
- GET /health        – health check
"""
import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="API Documentation",
    version="1.0.0",
    description="Unified API documentation for all public microservice APIs (as exposed via API Gateway).",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_here = Path(__file__).resolve().parent
# Specs live in this service's specs/ folder (registry + per-service YAMLs)
_specs_dir = _here / "specs"
REGISTRY_ENV = "SERVICE_DOCS_REGISTRY_PATH"
GATEWAY_URL_ENV = "API_GATEWAY_URL"
DEFAULT_GATEWAY_URL = "http://localhost:8080"
DEFAULT_REGISTRY = _specs_dir / "service-docs-registry.yaml"
SPECS_ROOT_ENV = "SPECS_ROOT"


def _registry_path() -> Path:
    path = os.getenv(REGISTRY_ENV)
    if path:
        return Path(path)
    return DEFAULT_REGISTRY


def _specs_root_path() -> Path:
    """Root for resolving spec_file paths (this service's specs/ dir, or SPECS_ROOT env)."""
    root = os.getenv(SPECS_ROOT_ENV)
    if root:
        return Path(root)
    return _specs_dir


def _gateway_url() -> str | None:
    """Return API_GATEWAY_URL from env if set, else None (caller can fall back to registry)."""
    val = os.getenv(GATEWAY_URL_ENV)
    return val.rstrip("/") if val else None


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"api_gateway_url": _gateway_url() or DEFAULT_GATEWAY_URL, "services": {}}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {"services": {}}


def _load_spec_file(rel_path: str) -> dict[str, Any] | None:
    """Load a single OpenAPI spec (YAML or JSON). Path relative to specs root (e.g. asr-service.yaml)."""
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
    """Merge components/schemas from incoming into base with prefix to avoid clashes. Rewrite $refs inside schemas so they point to prefixed names."""
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
    """Merge components/responses from incoming into base with prefix. Rewrite $refs inside responses."""
    inc_resp = (incoming.get("components") or {}).get("responses") or {}
    if not inc_resp:
        return
    base_components = base.setdefault("components", {})
    base_resp = base_components.setdefault("responses", {})
    for name, resp in inc_resp.items():
        base_resp[f"{prefix}_{name}"] = _rewrite_refs(resp, prefix, prefix)


def _rewrite_refs(obj: Any, schema_prefix: str, response_prefix: str) -> Any:
    """Rewrite $ref in a copy of obj to use prefixed component names."""
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
    """Use only the registry tag so the merged doc has one section per service."""
    op = dict(op)
    op["tags"] = [tag]
    return op


def _merge_paths(
    base: dict[str, Any],
    incoming: dict[str, Any],
    tag: str,
    schema_prefix: str,
    response_prefix: str,
) -> None:
    """Merge paths from incoming into base. Ensure operations have tag. Rewrite $refs to prefixed components."""
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
    """Display tag for a service in the merged spec."""
    tag = (meta.get("description") or service_name).strip()
    return tag or service_name.replace("-", " ").title()


def _add_service_spec(
    merged: dict[str, Any],
    service_name: str,
    meta: dict[str, Any],
    seen_tags: set[str],
) -> None:
    """Load one service spec and merge into merged; update seen_tags."""
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
    """Build a single OpenAPI 3.0 spec from all service spec files in the registry."""
    registry = _load_registry()
    # Env API_GATEWAY_URL overrides registry so deployment/docker can set the server URL
    gateway_url = (_gateway_url() or registry.get("api_gateway_url") or DEFAULT_GATEWAY_URL).rstrip("/")
    services = registry.get("services") or {}

    merged: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": "AI4Inclusion APIs",
            "description": "A comprehensive microservices based platform to handle language based AI models inferences at scale.",
            "version": "1.0.0",
        },
        "servers": [
            {"url": gateway_url, "description": ""}
        ],
        "paths": {},
        "components": {"schemas": {}, "responses": {}, "securitySchemes": {}},
        "tags": [],
        "security": [{"BearerAuth": []}],
    }
    merged["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "API Key",
        "description": "API key in Authorization header (Bearer <key>)",
    }

    seen_tags: set[str] = set()
    for service_name, meta in services.items():
        _add_service_spec(merged, service_name, meta, seen_tags)

    if not merged["paths"]:
        merged["paths"]["/"] = {
            "get": {
                "tags": ["Status"],
                "summary": "Placeholder",
                "responses": {"200": {"description": "No service specs loaded."}},
            }
        }
        merged["tags"].insert(0, {"name": "Status", "description": "Status"})

    return merged


# Cache merged spec (reload on first request or when env changes; optional TTL could be added)
_merged_spec: dict[str, Any] | None = None


def _get_merged_spec() -> dict[str, Any]:
    global _merged_spec
    if _merged_spec is None:
        _merged_spec = _build_merged_spec()
    return _merged_spec


@app.get("/health")
def health():
    return {"status": "ok", "service": "docs-manager"}


@app.get("/openapi.json")
def openapi_json():
    """Single merged OpenAPI spec for all public APIs."""
    return JSONResponse(_get_merged_spec())


@app.get("/docs", response_class=HTMLResponse)
def swagger_ui():
    """Single Swagger UI showing all public APIs in one document."""
    spec_url = "/openapi.json"
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Public API Documentation</title>
  <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
  <style>
    /* Hide the spec URL input and Explore button */
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
    """Landing with link to single Swagger UI."""
    docs_url = "/docs"
    spec_url = "/openapi.json"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Documentation</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ color: #f8fafc; }}
    a {{ color: #38bdf8; }}
    a:hover {{ text-decoration: underline; }}
    .muted {{ color: #64748b; font-size: 0.9rem; margin-top: 1rem; }}
  </style>
</head>
<body>
  <h1>Public API Documentation</h1>
  <p>Single Swagger UI for all public microservice APIs (as exposed via API Gateway). Specs live in this service's <code>specs/</code> folder (registry + per-service YAMLs).</p>
  <p><a href="{docs_url}">Open Swagger UI</a></p>
  <p class="muted">OpenAPI spec: <a href="{spec_url}">{spec_url}</a></p>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/specs/{service_name}/openapi.json")
def service_openapi(service_name: str):
    """Per-service OpenAPI spec (from file)."""
    registry = _load_registry()
    services = registry.get("services") or {}
    if service_name not in services:
        return JSONResponse({"detail": f"Unknown service: {service_name}"}, status_code=404)
    spec_file = services[service_name].get("spec_file")
    if not spec_file:
        return JSONResponse({"detail": "No spec_file for service"}, status_code=404)
    spec = _load_spec_file(spec_file)
    if not spec:
        return JSONResponse({"detail": "Spec file not found"}, status_code=404)
    gateway_url = (_gateway_url() or registry.get("api_gateway_url") or DEFAULT_GATEWAY_URL).rstrip("/")
    spec["servers"] = [{"url": gateway_url, "description": "API Gateway"}]
    return JSONResponse(spec)

"""
Docs Manager — unified API documentation service.

Fetches OpenAPI specs from live services at startup and serves
Swagger UI with a category-grouped collapsible sidebar.

Endpoints:
  GET  /healthz                  — health + cache status
  GET  /specs                    — list of cached services grouped by category
  GET  /specs/{service_name}     — raw OpenAPI JSON for one service
  POST /specs/refresh            — re-fetch all specs from live services
  GET  /docs                     — Swagger UI (first available service)
  GET  /docs/{service_name}      — Swagger UI pre-loaded for a service
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.settings import settings
from app.services import spec_loader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_here = Path(__file__).resolve().parent.parent  # docs-manager root

REGISTRY_PATH = os.getenv(
    "SERVICE_DOCS_REGISTRY_PATH",
    str(_here / "specs" / "service-docs-registry.yaml"),
)
GATEWAY_URL = settings.gateway_url

_registry: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry
    _registry = spec_loader.load_registry(REGISTRY_PATH)
    await spec_loader.refresh_cache(_registry, host_suffix=settings.services_host_suffix)
    yield


app = FastAPI(
    title="API Documentation",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _all_service_names() -> List[str]:
    return sorted(spec_loader.get_cache().keys())


def _first_service() -> str:
    cache = spec_loader.get_cache()
    for cat in (_registry.get("categories") or {}).values():
        for svc_name in (cat.get("services") or {}):
            if svc_name in cache:
                return svc_name
    return next(iter(cache), "")


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return {"service": "docs-manager", "docs": "/docs", "specs": "/specs", "health": "/healthz"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    cache = spec_loader.get_cache()
    all_services = [
        svc_name
        for cat in (_registry.get("categories") or {}).values()
        for svc_name in (cat.get("services") or {})
    ]
    missing = [s for s in all_services if s not in cache]
    return {"status": "ok", "cached": len(cache), "missing": missing}


@app.get("/specs", response_class=JSONResponse)
def list_specs():
    cache = spec_loader.get_cache()
    groups: Dict[str, Dict] = {}
    for svc_name, svc in cache.items():
        cat = svc["category"]
        if cat not in groups:
            groups[cat] = {"category": cat, "category_label": svc["category_label"], "services": []}
        groups[cat]["services"].append({
            "name": svc_name,
            "label": svc["label"],
            "description": svc["description"],
        })
    return list(groups.values())


@app.post("/specs/refresh", response_class=JSONResponse)
async def refresh_specs():
    new_cache = await spec_loader.refresh_cache(_registry, host_suffix=settings.services_host_suffix)
    loaded = sorted(new_cache.keys())
    failed = sorted(
        svc_name
        for cat in (_registry.get("categories") or {}).values()
        for svc_name in (cat.get("services") or {})
        if svc_name not in new_cache
    )
    return {"loaded": loaded, "failed": failed, "total": len(loaded)}


_PUBLIC_ENDPOINTS: set = {
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/auth/guest/login"),
    ("post", "/api/v1/auth/forgot-password"),
    ("post", "/api/v1/auth/reset-password"),
    ("get",  "/api/v1/auth/validate"),
    ("get",  "/api/v1/auth/.well-known/jwks.json"),
}


def _strip_security_from_public_endpoints(spec: dict) -> None:
    for path, path_item in (spec.get("paths") or {}).items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            if (method.lower(), path) in _PUBLIC_ENDPOINTS:
                operation["security"] = []


@app.get("/specs/{service_name}", response_class=JSONResponse)
def get_spec(service_name: str):
    cache = spec_loader.get_cache()
    if service_name not in cache:
        return JSONResponse(
            status_code=404,
            content={"error": "service not found", "available": _all_service_names()},
        )
    spec = dict(cache[service_name]["spec"])
    spec["servers"] = [{"url": GATEWAY_URL, "description": "API Gateway"}]
    spec.setdefault("components", {}).setdefault("securitySchemes", {})
    spec["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    # Apply auth globally, then strip it from endpoints that are explicitly public
    spec["security"] = [{"BearerAuth": []}]
    _strip_security_from_public_endpoints(spec)
    return spec


@app.get("/docs", response_class=HTMLResponse)
def swagger_ui_default():
    first = _first_service()
    if not first:
        return HTMLResponse("<h2>No services loaded yet. Try POST /specs/refresh</h2>", status_code=503)
    return _swagger_html(first)


@app.get("/docs/{service_name}", response_class=HTMLResponse)
def swagger_ui_service(service_name: str):
    if service_name not in spec_loader.get_cache():
        return HTMLResponse(
            f"<h2>Service '{service_name}' not found or unavailable.</h2>"
            f"<p>Available: {', '.join(_all_service_names())}</p>",
            status_code=404,
        )
    return _swagger_html(service_name)


# ── Swagger UI HTML ───────────────────────────────────────────────────────────

def _swagger_html(active_service: str) -> HTMLResponse:
    cache = spec_loader.get_cache()
    categories = (_registry.get("categories") or {})

    sidebar_items = ""
    for cat_key, cat in categories.items():
        cat_label = cat.get("label", cat_key)
        services = cat.get("services") or {}

        sidebar_items += f"""
        <div class="category-block">
          <div class="category-header" onclick="toggleCategory('{cat_key}')">
            <span class="arrow" id="arrow-{cat_key}">▼</span>
            <span>{cat_label}</span>
          </div>
          <div class="category-services" id="cat-{cat_key}">
        """

        for svc_name, svc_meta in services.items():
            label = svc_meta.get("label", svc_name)
            available = svc_name in cache
            active_class = "active" if svc_name == active_service else ""
            unavailable_class = "unavailable" if not available else ""
            unavail_label = ' <span class="unavail-tag">(unavailable)</span>' if not available else ""
            onclick = f"loadSpec('{svc_name}')" if available else ""
            sidebar_items += (
                f'<div class="svc-item {active_class} {unavailable_class}" '
                f'id="svc-{svc_name}" onclick="{onclick}">'
                f"{label}{unavail_label}</div>"
            )

        sidebar_items += "</div></div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Documentation</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ display: flex; height: 100vh; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f3f4f6; }}
    #sidebar {{ width: 270px; min-width: 270px; background: #111827; color: #e5e7eb;
                overflow-y: auto; border-right: 1px solid #1f2937; padding: 14px 0; }}
    #sidebar h2 {{ padding: 0 18px 16px; margin-bottom: 10px;
                   border-bottom: 1px solid #374151;
                   font-size: 14px; font-weight: 700; color: #ffffff; letter-spacing: 0.05em; }}
    .category-block {{ margin-bottom: 8px; }}
    .category-header {{ display: flex; align-items: center; gap: 8px; padding: 10px 16px;
                        cursor: pointer; font-size: 12px; font-weight: 700;
                        text-transform: uppercase; letter-spacing: 0.06em;
                        color: #93c5fd; transition: background 0.2s ease; }}
    .category-header:hover {{ background: #1f2937; }}
    .arrow {{ font-size: 11px; transition: transform 0.2s ease; }}
    .arrow.collapsed {{ transform: rotate(-90deg); }}
    .category-services {{ overflow: hidden; }}
    .svc-item {{ padding: 9px 18px 9px 38px; font-size: 13px; color: #d1d5db;
                 cursor: pointer; border-left: 3px solid transparent; transition: all 0.15s ease; }}
    .svc-item:hover {{ background: #1f2937; color: #ffffff; }}
    .svc-item.active {{ background: #1e3a8a; border-left-color: #60a5fa;
                        color: #ffffff; font-weight: 600; }}
    .svc-item.unavailable {{ color: #6b7280; cursor: default; }}
    .svc-item.unavailable:hover {{ background: transparent; color: #6b7280; }}
    .unavail-tag {{ font-size: 10px; color: #9ca3af; }}
    #swagger-container {{ flex: 1; overflow-y: auto; background: #ffffff; }}
    .swagger-ui .topbar {{ display: none; }}
    .swagger-ui .information-container {{ padding: 10px 20px 0; }}
  </style>
</head>
<body>
  <div id="sidebar">
    <h2>API Docs</h2>
    {sidebar_items}
  </div>
  <div id="swagger-container">
    <div id="swagger-ui"></div>
  </div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    var currentService = "{active_service}";
    var ui;

    function initSwagger(serviceName) {{
      ui = SwaggerUIBundle({{
        url: "/specs/" + serviceName,
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        layout: "BaseLayout",
        persistAuthorization: true,
        deepLinking: false,
        displayRequestDuration: true,
        filter: true,
      }});
    }}

    function loadSpec(serviceName) {{
      document.querySelectorAll(".svc-item").forEach(function(el) {{
        el.classList.remove("active");
      }});
      var el = document.getElementById("svc-" + serviceName);
      if (el) el.classList.add("active");
      currentService = serviceName;
      window.history.replaceState(null, "", "/docs/" + serviceName);
      initSwagger(serviceName);
    }}

    function toggleCategory(categoryKey) {{
      var container = document.getElementById("cat-" + categoryKey);
      var arrow = document.getElementById("arrow-" + categoryKey);
      if (container.style.display === "none") {{
        container.style.display = "block";
        arrow.classList.remove("collapsed");
      }} else {{
        container.style.display = "none";
        arrow.classList.add("collapsed");
      }}
    }}

    window.onload = function() {{ initSwagger(currentService); }};
  </script>
</body>
</html>"""
    return HTMLResponse(html)

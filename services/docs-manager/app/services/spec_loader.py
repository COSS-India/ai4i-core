"""
spec_loader — fetch and cache OpenAPI specs from live services.

All fetch + cache logic lives here. No FastAPI imports.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import httpx
import yaml

logger = logging.getLogger(__name__)

_spec_cache: Dict[str, Any] = {}


def get_cache() -> Dict[str, Any]:
    return _spec_cache


def load_registry(yaml_path: str) -> dict:
    path = Path(yaml_path)
    if not path.exists():
        logger.error("Registry file not found: %s", yaml_path)
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def resolve_spec_url(spec_url: str, host_suffix: str) -> str:
    """
    Apply SERVICES_HOST_SUFFIX to a spec_url hostname.

    Examples:
      host_suffix=""                          → URL unchanged (Docker / K8s same namespace)
      host_suffix=".dev.svc.cluster.local"   → http://ner-service:9001/openapi.json
                                             → http://ner-service.dev.svc.cluster.local:9001/openapi.json
    """
    if not host_suffix:
        return spec_url
    parsed = urlparse(spec_url)
    hostname = parsed.hostname or ""
    port = parsed.port
    new_netloc = f"{hostname}{host_suffix}:{port}" if port else f"{hostname}{host_suffix}"
    return urlunparse(parsed._replace(netloc=new_netloc))


async def fetch_spec(
    service_name: str,
    spec_url: str,
    optional: bool,
) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(spec_url)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        if optional:
            logger.warning("Skipping %s (unreachable): %s", service_name, exc)
        else:
            logger.error("Failed to fetch spec for %s from %s: %s", service_name, spec_url, exc)
        return None


async def load_all_specs(registry: dict, host_suffix: str = "") -> Dict[str, Any]:
    categories = registry.get("categories") or {}

    tasks = []
    meta_list = []

    for cat_key, cat in categories.items():
        cat_label = cat.get("label", cat_key)
        optional = cat.get("optional", False)
        services = cat.get("services") or {}
        for svc_name, svc_meta in services.items():
            yaml_url = svc_meta.get("spec_url")
            if not yaml_url:
                continue
            spec_url = resolve_spec_url(yaml_url, host_suffix)
            tasks.append(fetch_spec(svc_name, spec_url, optional))
            meta_list.append({
                "name": svc_name,
                "label": svc_meta.get("label", svc_name),
                "description": svc_meta.get("description", ""),
                "category": cat_key,
                "category_label": cat_label,
                "spec_url": spec_url,
            })

    results = await asyncio.gather(*tasks)

    cache: Dict[str, Any] = {}
    loaded = []
    skipped = []

    for meta, spec in zip(meta_list, results):
        if spec is not None:
            cache[meta["name"]] = {
                "spec": spec,
                "label": meta["label"],
                "description": meta["description"],
                "category": meta["category"],
                "category_label": meta["category_label"],
                "spec_url": meta["spec_url"],
            }
            loaded.append(meta["name"])
        else:
            skipped.append(meta["name"])

    if loaded:
        logger.info("✓ Loaded:  %s", ", ".join(loaded))
    if skipped:
        logger.warning("✗ Skipped: %s", ", ".join(skipped))

    return cache


async def refresh_cache(registry: dict, host_suffix: str = "") -> Dict[str, Any]:
    global _spec_cache
    new_cache = await load_all_specs(registry, host_suffix)
    _spec_cache = new_cache
    return _spec_cache

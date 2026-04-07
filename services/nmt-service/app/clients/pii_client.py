"""
Client for PII Guardrail /redact -- used only when persisting NMT text to the database.

PII patterns and NER are only reliable for the languages the guardrail ships with (en, hi, mr, ta).
For other language pairs, we skip redaction and store the raw strings.
"""

from __future__ import annotations

from typing import Dict, Optional

import httpx

# Matches pattern coverage in pii-service (pattern_library "all" -> en, hi, mr, ta).
PII_SUPPORTED_LANG_CODES = frozenset({"en", "hi", "mr", "ta"})


def pii_language_code(raw: str) -> str:
    """Strip script suffix (e.g. hi_Deva -> hi) for PII language header."""
    if not raw:
        return ""
    return raw.split("_", 1)[0].strip().lower()


async def redact_for_storage(
    *,
    base_url: str,
    text: str,
    lang: str,
    auth_headers: Optional[Dict[str, str]],
    tenant_id: Optional[str],
    timeout: float,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """
    POST /redact with x-language. Returns redacted_text on success.
    Raises httpx.HTTPError or ValueError on failure.
    """
    url = f"{base_url.rstrip('/')}/redact"
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "x-language": lang,
        "x-target": "user",
    }
    if auth_headers:
        headers.update(auth_headers)
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id

    if client is not None:
        response = await client.post(url, json={"text": text}, headers=headers, timeout=timeout)
    else:
        async with httpx.AsyncClient() as temp_client:
            response = await temp_client.post(url, json={"text": text}, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    out = payload.get("redacted_text")
    if out is None:
        raise ValueError("PII response missing redacted_text")
    return str(out)

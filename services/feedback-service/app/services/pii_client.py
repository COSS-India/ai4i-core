"""
PII redaction client — thin wrapper around the pii-guard-service /redact endpoint.

Redaction is performed before any user-supplied text is written to the database.
If the PII service is unavailable or the language is unsupported the original text
is returned unchanged and a warning is logged — the feedback write succeeds, ops must
ensure pii-guard-service is healthy for compliance.

Language support mirrors the pii-guard-service pattern library (en, hi, mr, ta).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PII_SUPPORTED_LANG_CODES = frozenset({"en", "hi", "mr", "ta"})


def _pii_base_url() -> str:
    return os.getenv("PII_SERVICE_URL", "http://pii-guard-service:8000").rstrip("/")


def _pii_timeout() -> float:
    return float(os.getenv("PII_TIMEOUT_SECONDS", "3.0"))


def _lang_code(raw: str) -> str:
    """Normalise a raw language code: strip script suffix (hi_Deva → hi)."""
    return raw.split("_", 1)[0].strip().lower() if raw else ""


def _source_lang(language: Optional[str]) -> str:
    """Extract source language from a 'hi-en' or plain 'hi' string."""
    if not language:
        return ""
    return _lang_code(language.split("-")[0])


def _target_lang(language: Optional[str]) -> str:
    """Extract target language from a 'hi-en' string; falls back to source."""
    if not language:
        return ""
    parts = language.split("-")
    return _lang_code(parts[1] if len(parts) > 1 else parts[0])


async def redact(
    text: str,
    lang_code: str,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Redact PII in *text* using the pii-guard-service.

    Returns the original text unchanged when:
    - text is empty
    - language is not in PII_SUPPORTED_LANG_CODES
    - the service call fails (logs a warning)
    """
    if not text:
        return text
    if lang_code not in PII_SUPPORTED_LANG_CODES:
        return text

    try:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-language": lang_code,
            "x-target": "user",
        }
        if tenant_id:
            headers["X-Tenant-Id"] = tenant_id

        async with httpx.AsyncClient(timeout=_pii_timeout()) as client:
            resp = await client.post(
                f"{_pii_base_url()}/redact",
                json={"text": text},
                headers=headers,
            )
            resp.raise_for_status()
            redacted = resp.json().get("redacted_text")
            if redacted is None:
                raise ValueError("PII response missing redacted_text field")
            return str(redacted)
    except Exception as exc:
        logger.warning("PII redaction skipped (falling back to original): %s", exc)
        return text


async def redact_pair(
    source_input: str,
    model_output: str,
    language: Optional[str],
    tenant_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Redact a (source_input, model_output) pair.

    source_input is redacted using the source language; model_output using the
    target language extracted from the 'src-tgt' language field.
    """
    src_lang = _source_lang(language)
    tgt_lang = _target_lang(language)
    redacted_source, redacted_output = await asyncio.gather(
        redact(source_input, src_lang, tenant_id),
        redact(model_output, tgt_lang, tenant_id),
    )
    return redacted_source, redacted_output

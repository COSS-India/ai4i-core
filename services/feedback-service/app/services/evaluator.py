"""
LLM Judge evaluator for translation / AI output quality assessment.

Supports single-record and batch evaluation against an Ollama-compatible
LLM endpoint. Results are written back to the FeedbackMetric table.
"""

import asyncio
import json
import logging
import re
from typing import List

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackMetric

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config (read from environment via ai4icore_env)
# ---------------------------------------------------------------------------

def _llm_judge_url() -> str:
    import os
    return os.getenv("LLM_JUDGE_URL", "http://localhost:11434/api/generate")


def _llm_model() -> str:
    import os
    return os.getenv("LLM_JUDGE_MODEL", "llama3:8b")


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

ERROR_CATEGORIES = (
    "Meaning Errors",
    "Grammar Errors",
    "Terminology Errors",
    "Pronunciation/Acoustic Errors",
    "Structural/Alignment Errors",
    "Context/Pragmatic Errors",
    "Formatting/Script Errors",
    "Robustness Errors",
)

# ---------------------------------------------------------------------------
# Single-record evaluation
# ---------------------------------------------------------------------------

_SINGLE_PROMPT = """[INST] You are an expert linguistic judge evaluating AI-generated output quality.

Task type: {task_type}
Language: {language}
Source input: "{source}"
Model output: "{output}"

CRITICAL GUARDRAILS:
- Judge the OUTPUT against the SOURCE — do not confuse source and target languages.
- Return ONLY valid JSON, no markdown, no prose.

Error categories (use exact name or "None"):
{categories}

OUTPUT FORMAT:
{{
    "status": "PASS" or "FAIL",
    "error_type": "<category name>" or "None",
    "severity": "HIGH", "MEDIUM", or "LOW",
    "reasoning": "<brief explanation>"
}}
[/INST]"""


async def evaluate_single(record_id: str, source: str, output: str,
                           task_type: str, language: str, db: AsyncSession) -> None:
    """Evaluate a single record and persist results."""
    prompt = _SINGLE_PROMPT.format(
        task_type=task_type,
        language=language or "unknown",
        source=source,
        output=output,
        categories="\n".join(f"- {c}" for c in ERROR_CATEGORIES),
    )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                _llm_judge_url(),
                json={
                    "model": _llm_model(),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_ctx": 4096},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")

        result = _parse_json_object(raw)
        if not result:
            raise ValueError(f"No valid JSON in LLM response: {raw[:200]}")

        res = await db.execute(select(FeedbackMetric).where(FeedbackMetric.id == uuid.UUID(record_id)))
        record = res.scalar_one_or_none()
        if not record:
            return

        record.ai_status = result.get("status", "ERROR")
        record.error_type = result.get("error_type") or None
        record.severity = result.get("severity") or None
        payload = dict(record.payload or {})
        payload["ai_reasoning"] = result.get("reasoning", "")
        record.payload = payload
        await db.commit()

    except Exception as exc:
        logger.error("evaluate_single failed for %s: %s", record_id, exc)
        res = await db.execute(select(FeedbackMetric).where(FeedbackMetric.id == uuid.UUID(record_id)))
        record = res.scalar_one_or_none()
        if record:
            record.ai_status = "ERROR"
            payload = dict(record.payload or {})
            payload["error"] = str(exc)
            record.payload = payload
            await db.commit()


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------

_BATCH_PROMPT = """[INST] You are an expert linguistic judge. Evaluate the following AI output items.

CRITICAL GUARDRAILS:
- Evaluate each OUTPUT against its SOURCE independently.
- Return ONLY a JSON array — no markdown, no prose.
- Array must have exactly {count} objects in the same order as the input.

Error categories (use exact name or "None"):
{categories}

Items:
{items}

OUTPUT FORMAT (array of {count} objects):
[
  {{
    "status": "PASS" or "FAIL",
    "error_type": "<category>" or "None",
    "severity": "HIGH", "MEDIUM", or "LOW",
    "reason": "<brief explanation>"
  }},
  ...
]
[/INST]"""

_BATCH_SIZE = 5
_BATCH_CONCURRENCY = 1


async def evaluate_batch(records: List[FeedbackMetric], db: AsyncSession) -> None:
    """Evaluate records in batches of _BATCH_SIZE with controlled concurrency."""
    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)
    chunks = [records[i:i + _BATCH_SIZE] for i in range(0, len(records), _BATCH_SIZE)]
    await asyncio.gather(*[_evaluate_chunk(chunk, db, semaphore) for chunk in chunks])


async def _evaluate_chunk(chunk: List[FeedbackMetric], db: AsyncSession,
                           semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        items_text = "\n".join(
            f"{i + 1}. task={r.task_type} lang={r.language or 'unknown'} "
            f'source="{r.source_input}" output="{r.model_output}"'
            for i, r in enumerate(chunk)
        )
        prompt = _BATCH_PROMPT.format(
            count=len(chunk),
            categories="\n".join(f"- {c}" for c in ERROR_CATEGORIES),
            items=items_text,
        )

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    _llm_judge_url(),
                    json={
                        "model": _llm_model(),
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_ctx": 8192},
                    },
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "")

            results = _parse_json_array(raw)
            if not results or len(results) != len(chunk):
                raise ValueError(
                    f"Expected {len(chunk)} results, got {len(results) if results else 0}. "
                    f"Raw: {raw[:300]}"
                )

            for record, result in zip(chunk, results):
                record.ai_status = result.get("status", "ERROR")
                record.error_type = result.get("error_type") or None
                record.severity = result.get("severity") or None
                payload = dict(record.payload or {})
                payload["ai_reasoning"] = result.get("reason", "")
                record.payload = payload

            await db.commit()

        except Exception as exc:
            logger.error("_evaluate_chunk failed: %s", exc)
            for record in chunk:
                record.ai_status = "ERROR"
                payload = dict(record.payload or {})
                payload["error"] = str(exc)
                record.payload = payload
            await db.commit()


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _parse_json_array(text: str) -> list:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []

"""PII policy guardrail for LLM inference.

Flow per request:
  1. get_policy_ids_for_app   — read auth:app:{id}:policy_ids from Redis
  2. get_policy               — read policy:{id} from Redis; re-cache on miss
  3. apply_input_guardrail    — mask PII in messages before sending to LLM
  4. apply_output_guardrail   — mask PII in LLM response (output/both scope)
  5. unmask_response          — replace <TYPE_N> tokens back with originals
  6. write_audit_log          — fire-and-forget POST to platform-core /internal

Masking reuses simulation.py's _build_recognizers so both field types work:
  - custom_field         → TimedPatternRecognizer (regex-based)
  - model_supported_field → Presidio built-in recognizers, per language
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
import redis.asyncio as aioredis

from config import settings
from services.pii.engine import get_engine
from services.pii.language import DEFAULT_LANGUAGE, detect_language
from services.pii.simulation import CustomField, PolicyType, _build_recognizers

logger = logging.getLogger(__name__)

_APP_POLICY_KEY = "auth:app:{}:policy_ids"
_POLICY_KEY = "policy:{}"

_redis_client: Optional[aioredis.Redis] = None


def _get_redis() -> Optional[aioredis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                socket_timeout=settings.REDIS_TIMEOUT,
                decode_responses=True,
            )
        except Exception as exc:
            logger.warning("Guardrail Redis init failed: %s", exc)
    return _redis_client


# ── Redis helpers ────────────────────────────────────────────────────────────

async def get_policy_ids_for_app(app_id: str) -> List[int]:
    redis = _get_redis()
    if redis is None:
        return []
    try:
        raw = await redis.get(_APP_POLICY_KEY.format(app_id))
        return json.loads(raw) if raw else []
    except Exception as exc:
        logger.warning("Failed to read policy_ids for app_id=%s: %s", app_id, exc)
        return []


async def get_policy(policy_id: int) -> Optional[Dict]:
    """Return policy from Redis. On miss: fetch from platform-core and re-cache."""
    redis = _get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(_POLICY_KEY.format(policy_id))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis read failed for policy_id=%s: %s", policy_id, exc)

    if not settings.PLATFORM_CORE_URL:
        return None
    try:
        headers = {}
        if settings.PLATFORM_CORE_INTERNAL_TOKEN:
            headers["X-Internal-Service-Token"] = settings.PLATFORM_CORE_INTERNAL_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.PLATFORM_CORE_URL}/api/v1/policy-service/policies/{policy_id}",
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json().get("data") or r.json()
            if redis:
                try:
                    await redis.set(_POLICY_KEY.format(policy_id), json.dumps(data), ex=300)
                except Exception:
                    pass
            return data
    except Exception as exc:
        logger.warning("Failed to re-fetch policy_id=%s from platform-core: %s", policy_id, exc)
    return None


# ── Policy parsing ────────────────────────────────────────────────────────────

def _parse_policy_types(policy: Dict) -> List[PolicyType]:
    """Convert policy dict from Redis into PolicyType objects for simulation.py's
    _build_recognizers.

    policy_fields structure (flat, no domain wrapper):
      {
        "custom_field": [{"entity_name": "...", "regex": "..."}, ...],
        "model_supported_field": [{"en": ["PERSON", "EMAIL_ADDRESS"]}, ...]
      }
    """
    result = []
    for pt in policy.get("policy_types") or []:
        pf = pt.get("policy_fields") or {}

        custom_fields = [
            CustomField(entity_name=cf["entity_name"], regex=cf["regex"])
            for cf in pf.get("custom_field") or []
            if cf.get("entity_name") and cf.get("regex")
        ]

        # model_supported_field: list of {lang_code: [entity_names]}
        model_entities: Dict[str, List[str]] = {}
        for entry in pf.get("model_supported_field") or []:
            if isinstance(entry, dict):
                for lang, names in entry.items():
                    if isinstance(names, list):
                        entity_names = [
                            n["entity_name"] if isinstance(n, dict) else n
                            for n in names
                            if (isinstance(n, dict) and n.get("entity_name")) or isinstance(n, str)
                        ]
                        model_entities.setdefault(lang, []).extend(entity_names)

        result.append(PolicyType(
            name=pt.get("policy_type") or "PII",
            custom_fields=custom_fields,
            model_entities=model_entities,
        ))
    return result


# ── Masking ───────────────────────────────────────────────────────────────────

def _mask(text: str, policy_types: List[PolicyType]) -> Tuple[str, Dict[str, str]]:
    """Analyze + anonymize text using both custom regex and Presidio built-in recognizers.

    - custom_field         → TimedPatternRecognizer (via _build_recognizers)
    - model_supported_field → Presidio built-in NER/pattern recognizers

    Returns (masked_text, token_to_original).
    """
    # Detect language from the languages the policy covers
    policy_languages = {lang for pt in policy_types for lang in pt.model_entities}
    language = detect_language(text, policy_languages) if policy_languages else DEFAULT_LANGUAGE

    recs = _build_recognizers(policy_types, language)
    if not recs.sources:
        logger.info("No recognizers built — text sent as-is")
        return text, {}

    engine = get_engine()

    # Run custom regex recognizers
    analyzer_results = [
        result
        for recognizer in recs.ad_hoc
        for result in recognizer.analyze(text, recognizer.supported_entities)
    ]

    # Run Presidio built-in recognizers for model_supported entities
    if recs.model_entities:
        detectable = recs.model_entities - engine.detectable_entities(language)
        entities_to_detect = recs.model_entities - detectable  # subtract undetectable
        if entities_to_detect:
            analyzer_results += engine.analyze(text, language, entities=sorted(entities_to_detect))

    if not analyzer_results:
        logger.info("No PII detected — text sent as-is")
        return text, {}

    logger.info("── PRESIDIO ANALYZE ──────────────────────────")
    logger.info("Input text   : %s", text)
    logger.info("Language     : %s", language)
    for r in analyzer_results:
        logger.info("  entity=%-20s start=%-4d end=%-4d score=%.2f  value=%r",
                    r.entity_type, r.start, r.end, r.score, text[r.start:r.end])

    anonymized, entity_mapping = engine.anonymize(text, analyzer_results)

    logger.info("── PRESIDIO ANONYMIZE ────────────────────────")
    logger.info("Masked text  : %s", anonymized.text)
    for entity_type, mapping in entity_mapping.items():
        for original, token in mapping.items():
            logger.info("  %-20s  %r  →  %s", entity_type, original, token)

    # Invert {entity_type: {original: token}} → {token: original}
    token_to_original = {
        token: original
        for per_type in entity_mapping.values()
        for original, token in per_type.items()
    }
    return anonymized.text, token_to_original


def _mask_messages(
    messages: List[Dict], policy_types: List[PolicyType]
) -> Tuple[List[Dict], Dict[str, str]]:
    """Mask PII across all message contents. Accumulates token→original map."""
    combined: Dict[str, str] = {}
    masked = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and content:
            masked_content, token_map = _mask(content, policy_types)
            combined.update(token_map)
            masked.append({**msg, "content": masked_content})
        else:
            masked.append(msg)
    return masked, combined


def _unmask(text: str, token_to_original: Dict[str, str]) -> str:
    for token, original in token_to_original.items():
        text = text.replace(token, original)
    return text


# ── Guardrail context ─────────────────────────────────────────────────────────

@dataclass
class GuardrailContext:
    applied_policy_ids: List[int] = field(default_factory=list)
    policy_types: List[PolicyType] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)      # "input" / "output" / "both"
    token_to_original: Dict[str, str] = field(default_factory=dict)

    @property
    def needs_input_mask(self) -> bool:
        return any(s in ("input", "both") for s in self.scopes)

    @property
    def needs_output_mask(self) -> bool:
        return any(s in ("output", "both") for s in self.scopes)

    @property
    def active(self) -> bool:
        return bool(self.applied_policy_ids)


async def build_guardrail_context(app_id: str) -> GuardrailContext:
    ctx = GuardrailContext()
    policy_ids = await get_policy_ids_for_app(app_id)
    if not policy_ids:
        return ctx

    for pid in policy_ids:
        policy = await get_policy(pid)
        if not policy or not policy.get("is_active"):
            continue
        ctx.applied_policy_ids.append(pid)
        ctx.policy_types.extend(_parse_policy_types(policy))
        scope = policy.get("guardrail_scope") or ""
        if scope:
            ctx.scopes.append(scope)
    return ctx


# ── Input / output guardrail ──────────────────────────────────────────────────

def apply_input_guardrail(
    payload: Dict[str, Any], ctx: GuardrailContext
) -> Dict[str, Any]:
    if not ctx.needs_input_mask or not ctx.policy_types:
        return payload
    messages = payload.get("messages") or []
    logger.info("Payload BEFORE masking: %s", messages)
    masked_messages, ctx.token_to_original = _mask_messages(messages, ctx.policy_types)
    if ctx.token_to_original:
        logger.info("Guardrail masked %d PII value(s): %s",
                    len(ctx.token_to_original), list(ctx.token_to_original.values()))
    logger.info("Payload AFTER  masking: %s", masked_messages)
    return {**payload, "messages": masked_messages}


def apply_output_guardrail(response_text: str, ctx: GuardrailContext) -> str:
    if not ctx.needs_output_mask or not ctx.policy_types:
        return response_text
    masked, _ = _mask(response_text, ctx.policy_types)
    return masked


def unmask_response(response_text: str, ctx: GuardrailContext) -> str:
    if not ctx.token_to_original:
        return response_text
    return _unmask(response_text, ctx.token_to_original)


def process_response_text(response_text: str, ctx: GuardrailContext) -> str:
    """Unmask input tokens then apply output masking (in correct order)."""
    if ctx.needs_input_mask:
        response_text = unmask_response(response_text, ctx)
    if ctx.needs_output_mask:
        response_text = apply_output_guardrail(response_text, ctx)
    return response_text


# ── Audit log (fire-and-forget) ───────────────────────────────────────────────

async def _write_audit_log(
    policy_ids: List[int],
    trace_id: Optional[str],
    model_request: Dict,
    response: Dict,
    guardrail_info: Dict,
    created_by: Optional[str],
) -> None:
    if not settings.PLATFORM_CORE_URL:
        return
    try:
        headers = {"Content-Type": "application/json"}
        if settings.PLATFORM_CORE_INTERNAL_TOKEN:
            headers["X-Internal-Service-Token"] = settings.PLATFORM_CORE_INTERNAL_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.PLATFORM_CORE_URL}/internal/policy-audit-logs",
                json={
                    "policy_id": policy_ids,
                    "trace_id": trace_id,
                    "model_request": model_request,
                    "response": response,
                    "guardrail_info": guardrail_info,
                    "created_by": created_by,
                },
                headers=headers,
            )
    except Exception as exc:
        logger.warning("Audit log write failed (policy_ids=%s): %s", policy_ids, exc)


def schedule_audit_log(
    ctx: GuardrailContext,
    trace_id: Optional[str],
    model_request: Dict,
    response: Dict,
    app_id: Optional[str],
) -> None:
    asyncio.create_task(
        _write_audit_log(
            policy_ids=ctx.applied_policy_ids,
            trace_id=trace_id,
            model_request=model_request,
            response=response,
            guardrail_info={
                "scopes": ctx.scopes,
                "custom_entities": [cf.entity_name for pt in ctx.policy_types for cf in pt.custom_fields],
                "model_entities": {lang: names for pt in ctx.policy_types for lang, names in pt.model_entities.items()},
            },
            created_by=app_id,
        )
    )

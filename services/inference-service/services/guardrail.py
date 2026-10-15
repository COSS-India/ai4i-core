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

_background_tasks: set = set()


class GuardrailError(Exception):
    """Raised when a PII policy cannot be evaluated or enforced.

    Any caller that catches this must block the request rather than
    letting it proceed without enforcement.
    """


class PolicyNotFoundError(GuardrailError):
    """platform-core has no policy with the requested id."""


class PolicyFieldsError(GuardrailError):
    """A policy type's policy_fields cannot be turned into recognizers.

    Skipping the bad part would mask less than the policy says, so the
    guardrail blocks the request and /pii/simulate returns 400.
    """


_APP_POLICY_KEY = "auth:app:{}:policy_ids"
_POLICY_KEY = "policy:{}"
_GLOBAL_POLICY_IDS_KEY = "global:policy_ids"
_GLOBAL_POLICY_IDS_BUILT_KEY = "global:policy_ids:built"  # sentinel: index fetched, empty result is valid
_GLOBAL_POLICY_IDS_TTL = 300

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
        raise GuardrailError(f"Redis unavailable — cannot read policies for app_id={app_id!r}")
    try:
        raw = await redis.get(_APP_POLICY_KEY.format(app_id))
        return json.loads(raw) if raw else []
    except Exception as exc:
        raise GuardrailError(f"Failed to read policy IDs for app_id={app_id!r}") from exc


async def get_global_policy_ids() -> List[int]:
    """Return IDs of all active global policies.

    Reads from the Redis Set written by platform-core's cache_policy. An empty
    smembers result is ambiguous (key evicted vs. genuinely no global policies),
    so a separate sentinel key (_GLOBAL_POLICY_IDS_BUILT_KEY) marks "index was
    built and is empty." Without the sentinel we fall back to platform-core.

    Raises GuardrailError on any fetch failure so callers block the request
    rather than silently skipping global policy enforcement.
    """
    redis = _get_redis()
    if redis is not None:
        try:
            members = await redis.smembers(_GLOBAL_POLICY_IDS_KEY)
            if members:
                return [int(m) for m in members]
            if await redis.exists(_GLOBAL_POLICY_IDS_BUILT_KEY):
                return []
        except Exception as exc:
            logger.warning("Redis read failed for global policy IDs: %s", exc)

    if not settings.PLATFORM_CORE_URL:
        raise GuardrailError(
            "Cannot fetch global policy IDs: PLATFORM_CORE_URL is not configured"
        )
    try:
        headers = {}
        if settings.PLATFORM_CORE_INTERNAL_TOKEN:
            headers["X-Internal-Service-Token"] = settings.PLATFORM_CORE_INTERNAL_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.PLATFORM_CORE_URL}/internal/policies/global",
                headers=headers,
            )
        if r.status_code != 200:
            raise GuardrailError(
                f"platform-core returned {r.status_code} for global policy IDs"
            )
        ids = r.json().get("data") or []
        if redis is not None:
            try:
                pipe = redis.pipeline()
                if ids:
                    pipe.delete(_GLOBAL_POLICY_IDS_KEY)
                    pipe.sadd(_GLOBAL_POLICY_IDS_KEY, *ids)
                    pipe.expire(_GLOBAL_POLICY_IDS_KEY, _GLOBAL_POLICY_IDS_TTL)
                pipe.set(_GLOBAL_POLICY_IDS_BUILT_KEY, "1", ex=_GLOBAL_POLICY_IDS_TTL)
                await pipe.execute()
            except Exception:
                pass
        return ids
    except GuardrailError:
        raise
    except Exception as exc:
        raise GuardrailError(
            "Failed to fetch global policy IDs from platform-core"
        ) from exc


async def get_policy(policy_id: int) -> Dict:
    """Return policy from Redis. On miss: fetch from platform-core and re-cache.

    Raises GuardrailError when the policy cannot be loaded from either source —
    callers must block the request rather than skip enforcement.
    """
    redis = _get_redis()
    try:
        if redis is not None:
            raw = await redis.get(_POLICY_KEY.format(policy_id))
            if raw:
                return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis read failed for policy_id=%s: %s", policy_id, exc)

    if not settings.PLATFORM_CORE_URL:
        raise GuardrailError(
            f"Cannot load policy_id={policy_id}: not in Redis and PLATFORM_CORE_URL not configured"
        )
    try:
        headers = {}
        if settings.PLATFORM_CORE_INTERNAL_TOKEN:
            headers["X-Internal-Service-Token"] = settings.PLATFORM_CORE_INTERNAL_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.PLATFORM_CORE_URL}/internal/policies/{policy_id}",
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
        if r.status_code == 404:
            raise PolicyNotFoundError(f"Policy {policy_id} not found")
        raise GuardrailError(
            f"Platform-core returned {r.status_code} for policy_id={policy_id}"
        )
    except GuardrailError:
        raise
    except Exception as exc:
        raise GuardrailError(
            f"Failed to fetch policy_id={policy_id} from platform-core"
        ) from exc


# ── Policy parsing ────────────────────────────────────────────────────────────

_POLICY_FIELD_KEYS = {"custom_field", "model_supported_field"}


def _non_blank_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _parse_policy_fields(name: str, pf: Any) -> PolicyType:
    if pf is None:
        pf = {}
    if not isinstance(pf, dict):
        raise PolicyFieldsError(f"{name}: policy_fields must be an object")
    unknown = sorted(set(pf) - _POLICY_FIELD_KEYS)
    if unknown:
        raise PolicyFieldsError(
            f"{name}: unknown policy_fields keys {unknown}; "
            "expected custom_field and model_supported_field"
        )

    custom = pf.get("custom_field") or []
    if not isinstance(custom, list):
        raise PolicyFieldsError(f"{name}: custom_field must be a list")
    # The same entity and regex listed twice runs once.
    custom_fields: List[CustomField] = []
    seen: set = set()
    for cf in custom:
        if not isinstance(cf, dict) or not (
            _non_blank_str(cf.get("entity_name")) and _non_blank_str(cf.get("regex"))
        ):
            raise PolicyFieldsError(
                f"{name}: each custom_field entry needs a string entity_name and regex"
            )
        key = (cf["entity_name"], cf["regex"])
        if key not in seen:
            seen.add(key)
            custom_fields.append(CustomField(entity_name=key[0], regex=key[1]))

    model = pf.get("model_supported_field") or []
    if not isinstance(model, list):
        raise PolicyFieldsError(f"{name}: model_supported_field must be a list")
    model_entities: Dict[str, List[str]] = {}
    for entry in model:
        if not isinstance(entry, dict):
            raise PolicyFieldsError(
                f"{name}: each model_supported_field item must map a language to a list"
            )
        for lang, entities in entry.items():
            if not isinstance(entities, list):
                raise PolicyFieldsError(
                    f"{name}: model_supported_field['{lang}'] must be a list"
                )
            # Listed even when empty: simulation detects the text's language
            # among the languages the policy names.
            names = model_entities.setdefault(lang, [])
            for e in entities:
                # platform-core stores {"entity_name": ...}; a bare name is accepted too.
                entity = e.get("entity_name") if isinstance(e, dict) else e
                if not _non_blank_str(entity):
                    raise PolicyFieldsError(
                        f"{name}: each model_supported_field['{lang}'] entry needs a "
                        "string entity_name"
                    )
                names.append(entity)

    return PolicyType(name=name, custom_fields=custom_fields, model_entities=model_entities)


def parse_policy_types(policy: Dict) -> List[PolicyType]:
    """Convert policy dict from Redis into PolicyType objects for simulation.py's
    _build_recognizers.

    policy_fields structure (flat, no domain wrapper):
      {
        "custom_field": [{"entity_name": "...", "regex": "..."}, ...],
        "model_supported_field": [{"en": [{"entity_name": "PERSON"}, ...]}, ...]
      }

    Raises PolicyFieldsError for anything else (e.g. the old {"Finance": {...}}
    domain wrapper) rather than dropping it and masking less than the policy says.
    """
    return [
        _parse_policy_fields(pt.get("policy_type") or "PII", pt.get("policy_fields"))
        for pt in policy.get("policy_types") or []
    ]


# ── Masking ───────────────────────────────────────────────────────────────────

def _mask(
    text: str,
    policy_types: List[PolicyType],
    entity_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> Tuple[str, Dict[str, str]]:
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
        undetectable = recs.model_entities - engine.detectable_entities(language)
        if undetectable:
            raise GuardrailError(
                f"Policy requires {sorted(undetectable)!r} but the engine cannot detect "
                f"them for language={language!r} — request blocked"
            )
        analyzer_results += engine.analyze(text, language, entities=sorted(recs.model_entities))

    if not analyzer_results:
        return text, {}

    anonymized, entity_mapping = engine.anonymize(text, analyzer_results, entity_mapping)

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
    """Mask PII across all message contents using one shared entity_mapping.

    A single entity_mapping dict is passed to every _mask call so the
    InstanceCounterAnonymizer counter is shared: "Alice" in msg1 gets
    <PERSON_1> and "Bob" in msg2 gets <PERSON_2> — never both <PERSON_1>.
    """
    shared_entity_mapping: Dict[str, Dict[str, str]] = {}
    masked = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and content:
            masked_content, _ = _mask(content, policy_types, shared_entity_mapping)
            masked.append({**msg, "content": masked_content})
        else:
            masked.append(msg)
    # Invert {entity_type: {original: token}} → {token: original} once for all messages
    token_to_original = {
        token: original
        for per_type in shared_entity_mapping.values()
        for original, token in per_type.items()
    }
    return masked, token_to_original


def _unmask(text: str, token_to_original: Dict[str, str]) -> str:
    for token, original in token_to_original.items():
        text = text.replace(token, original)
    return text


def _mask_for_audit_payload(payload: Dict, policy_types: List[PolicyType]) -> Dict:
    """Mask all message content in payload for audit, regardless of guardrail scope."""
    messages = payload.get("messages") or []
    if not messages:
        return payload
    masked_messages, _ = _mask_messages(messages, policy_types)
    return {**payload, "messages": masked_messages}


def _mask_for_audit_response(body: Dict, policy_types: List[PolicyType]) -> Dict:
    """Mask response content for audit, regardless of guardrail scope.

    Handles both buffered (choices[0].message.content) and stream synthetic
    (choices[0].delta.content) response shapes.
    """
    if not isinstance(body, dict):
        return body
    choices = body.get("choices") or []
    if not choices:
        return body
    first = choices[0]
    for key in ("message", "delta"):
        msg = first.get(key) or {}
        content = msg.get("content")
        if isinstance(content, str) and content:
            masked, _ = _mask(content, policy_types)
            return {
                **body,
                "choices": [{**first, key: {**msg, "content": masked}}, *choices[1:]],
            }
    return body


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


async def build_guardrail_context(app_id: Optional[str]) -> GuardrailContext:
    ctx = GuardrailContext()
    app_policy_ids = await get_policy_ids_for_app(app_id) if app_id else []
    global_policy_ids = await get_global_policy_ids()

    seen: set = set(app_policy_ids)
    policy_ids = list(app_policy_ids)
    for pid in global_policy_ids:
        if pid not in seen:
            policy_ids.append(pid)

    if not policy_ids:
        return ctx

    for pid in policy_ids:
        if not pid:
            continue
        policy = await get_policy(pid)  # raises GuardrailError if policy cannot be loaded
        if not policy.get("is_active"):
            continue
        category = policy.get("category")
        if category and not category.get("is_active"):
            continue
        sub_category = policy.get("sub_category")
        if sub_category and not sub_category.get("is_active"):
            continue
        # Raises PolicyFieldsError (a GuardrailError) for unusable policy_fields.
        policy_types = parse_policy_types(policy)
        ctx.applied_policy_ids.append(pid)
        ctx.policy_types.extend(policy_types)
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
    masked_messages, ctx.token_to_original = _mask_messages(messages, ctx.policy_types)
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
    policy_types: List[PolicyType],
) -> None:
    if not settings.PLATFORM_CORE_URL:
        return
    try:
        if policy_types:
            try:
                model_request = await asyncio.to_thread(_mask_for_audit_payload, model_request, policy_types)
                response = await asyncio.to_thread(_mask_for_audit_response, response, policy_types)
            except Exception as exc:
                logger.warning("Audit masking failed, redacting content from audit row (policy_ids=%s): %s", policy_ids, exc)
                model_request = {}
                response = {}
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
    status_code: int = 200,
) -> None:
    task = asyncio.create_task(
        _write_audit_log(
            policy_ids=ctx.applied_policy_ids,
            trace_id=trace_id,
            model_request=model_request,
            response=response,
            guardrail_info={
                "scopes": ctx.scopes,
                "status_code": status_code,
                "custom_entities": [cf.entity_name for pt in ctx.policy_types for cf in pt.custom_fields],
                "model_entities": {lang: names for pt in ctx.policy_types for lang, names in pt.model_entities.items()},
            },
            created_by=app_id,
            policy_types=ctx.policy_types,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

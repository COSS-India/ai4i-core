from fastapi import FastAPI, HTTPException, Request, Header, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import re
import os
import json
import time
import asyncpg
import httpx
import asyncio
from aiokafka import AIOKafkaProducer
from dotenv import load_dotenv
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
# Service-local .env (e.g. copy from env.template); optional if all vars come from the process env.
load_dotenv(_SERVICE_DIR / ".env")

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from ai4icore_exceptions import register_exception_handlers

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "pii_guardrail")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "secret")
NER_SERVICE_URL = os.getenv("NER_SERVICE_URL", "http://localhost:9001/ner")
POLICY_SERVICE_BASE_URL = os.getenv("POLICY_SERVICE_BASE_URL", "http://localhost:8107")
POLICY_SERVICE_TIMEOUT = float(os.getenv("POLICY_SERVICE_TIMEOUT", "5.0"))
POLICY_CACHE_TTL_SECONDS = int(os.getenv("POLICY_CACHE_TTL_SECONDS", "60"))
POLICY_CACHE_STALE_GRACE_SECONDS = int(os.getenv("POLICY_CACHE_STALE_GRACE_SECONDS", "300"))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_AUDIT_TOPIC = os.getenv("KAFKA_AUDIT_TOPIC", "pii_audit_logs")

db_pool = None
kafka_producer = None

app = FastAPI()
register_exception_handlers(app)

# Align with platform: shared telemetry (Jaeger OTLP, org processor, span filtering)
from ai4icore_env import app_env
from ai4icore_telemetry import setup_tracing

_pii_service_name = (
    (getattr(app_env, "service_name", None) or "").strip()
    or os.getenv("OTEL_SERVICE_NAME", "").strip()
    or "pii-service"
)
_tracer_setup = setup_tracing(_pii_service_name)
if _tracer_setup:
    FastAPIInstrumentor.instrument_app(app)

tracer = trace.get_tracer(_pii_service_name)

from middleware.auth_provider import AuthProvider


class KnowledgeBase:
    def __init__(self):
        self.patterns = {}
        self.suffixes = {}
        self.safe_geo = {}
        self.connected = False

    async def refresh(self):
        global db_pool
        for attempt in range(1, 11):
            try:
                print(f"Loading knowledge base attempt {attempt}...")
                async with db_pool.acquire() as conn:
                    pattern_rows = await conn.fetch(
                        "SELECT entity_label, lang_code, regex_pattern FROM pattern_library WHERE is_active = TRUE"
                    )
                    for row in pattern_rows:
                        lang, label = row["lang_code"], row["entity_label"]
                        langs = ["en", "hi", "mr", "ta"] if lang == "all" else [lang]
                        for l in langs:
                            self.patterns.setdefault(l, {})
                            try:
                                self.patterns[l][label] = re.compile(
                                    row["regex_pattern"], re.UNICODE | re.IGNORECASE
                                )
                            except re.error:
                                pass

                    geo_rows = await conn.fetch(
                        "SELECT term_text, lang_code, term_type FROM geo_library WHERE is_active = TRUE"
                    )
                    for row in geo_rows:
                        lang, term, typ = row["lang_code"], row["term_text"], row["term_type"]
                        if typ == "SUFFIX":
                            self.suffixes.setdefault(lang, []).append(term)
                        elif typ == "SAFE_CITY":
                            self.safe_geo.setdefault(lang, set()).add(term.lower())

                self.connected = True
                print("Knowledge base loaded")
                return
            except Exception as exc:
                print(f"Knowledge base load failed ({exc}), retrying...")
                await asyncio.sleep(3)
        print("Could not load knowledge base after retries")


KB = KnowledgeBase()


class DetectedEntity(BaseModel):
    entity_type: str
    start_index: int
    end_index: int
    text_segment: str
    detection_source: str
    risk_score: float = 0.0


class DetectionEngine:
    STOP_WORDS = {
        "en": {"is", "are", "am", "was", "were", "my", "our", "the", "a", "an", "at", "in", "on", "to", "from", "addr", "address", "lives", "living", "stay", "staying"},
        "hi": {"है", "हूँ", "हो", "था", "थे", "मेरा", "मेरी", "मेरे", "का", "की", "के", "में", "पर", "से", "पता", "रहता"},
        "mr": {"आहे", "होता", "होते", "माझा", "माझी", "माझे", "चा", "ची", "चे", "मध्ये", "वर", "ून", "पत्ता", "राहतो"},
        "ta": {"உள்ளது", "இருக்கிறது", "எனது", "என்", "முகவரி", "இல்", "இடத்தில்", "வசிப்பவர்", "எண்"},
    }

    FALSE_POSITIVES = {"phone", "mobile", "email", "address", "number", "फ़ोन", "मोबाइल", "ईमेल", "पता", "नंबर"}
    COMMON_OCCUPATIONS = {"farmer", "driver", "teacher", "engineer", "doctor", "nurse", "worker"}
    GENDER_TERMS = {"male", "female", "man", "woman", "boy", "girl", "transgender"}

    async def fetch_ai_entities(self, text: str, lang: str):
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(NER_SERVICE_URL, json={"text": text, "lang": lang}, timeout=3.0)
                if resp.status_code == 200:
                    return resp.json().get("entities", [])
            except Exception as exc:
                print(f"NER service call failed: {exc}")
            return []

    def detect_quasi_identifiers(self, text: str) -> List[DetectedEntity]:
        found: List[DetectedEntity] = []
        words = re.findall(r"\b\w+\b", text.lower())
        for w in words:
            if w in self.COMMON_OCCUPATIONS:
                for m in re.finditer(rf"\b{w}\b", text, re.IGNORECASE):
                    found.append(
                        DetectedEntity(
                            entity_type="OCCUPATION",
                            start_index=m.start(),
                            end_index=m.end(),
                            text_segment=m.group(),
                            detection_source="KEYWORD",
                            risk_score=0.3,
                        )
                    )
            if w in self.GENDER_TERMS:
                for m in re.finditer(rf"\b{w}\b", text, re.IGNORECASE):
                    found.append(
                        DetectedEntity(
                            entity_type="GENDER",
                            start_index=m.start(),
                            end_index=m.end(),
                            text_segment=m.group(),
                            detection_source="KEYWORD",
                            risk_score=0.2,
                        )
                    )
        return found

    async def detect(self, text: str, rules: List[Dict], trace_log: List, strict_mode: bool = False, lang: str = "en"):
        detected: List[DetectedEntity] = []
        t0 = time.time()

        patterns = KB.patterns.get(lang, {})
        active_types = [r["entity_type"] for r in rules]

        with tracer.start_as_current_span("pii_ai_extraction") as span:
            ai_count = 0
            external_ents = await self.fetch_ai_entities(text, lang)
            for ent in external_ents:
                ent_text = ent["text"]
                ent_label = ent["label"]
                if ent_text.lower() in self.FALSE_POSITIVES:
                    continue
                mapped = "LOCATION" if ent_label in ["GPE", "LOC", "FAC", "ORG"] else ent_label
                if ent_label == "PERSON":
                    mapped = "PERSON"
                if mapped in active_types:
                    detected.append(
                        DetectedEntity(
                            entity_type=mapped,
                            start_index=ent["start_char"],
                            end_index=ent["end_char"],
                            text_segment=ent_text,
                            detection_source=f"AI: {ent_label}",
                            risk_score=1.0 if strict_mode else 0.9,
                        )
                    )
                    ai_count += 1
            span.set_attribute("pii.ai_entities_found", ai_count)
            trace_log.append({"step": "AI Extraction", "status": "Success", "details": f"AI identified {ai_count} entities."})

        with tracer.start_as_current_span("pii_regex_scan") as span:
            regex_count = 0
            for rule in rules:
                if rule.get("custom_regex"):
                    try:
                        for m in re.finditer(rule["custom_regex"], text, re.UNICODE | re.IGNORECASE):
                            if m.lastindex and m.group(1):
                                val, st, en = m.group(1), m.start(1), m.end(1)
                            else:
                                val, st, en = m.group(), m.start(), m.end()
                            detected.append(
                                DetectedEntity(
                                    entity_type=rule["entity_type"],
                                    start_index=st,
                                    end_index=en,
                                    text_segment=val,
                                    detection_source="REGEX: Custom",
                                    risk_score=1.0,
                                )
                            )
                            regex_count += 1
                    except re.error:
                        pass
                lbl = rule["entity_type"]
                if lbl in patterns and not rule.get("custom_regex"):
                    for match in patterns[lbl].finditer(text):
                        if match.lastindex and match.group(1):
                            val, st, en = match.group(1), match.start(1), match.end(1)
                        else:
                            val, st, en = match.group(), match.start(), match.end()
                        if val.lower() in self.FALSE_POSITIVES:
                            continue
                        detected.append(
                            DetectedEntity(
                                entity_type=lbl,
                                start_index=st,
                                end_index=en,
                                text_segment=val,
                                detection_source=f"REGEX: {lbl}",
                                risk_score=1.0,
                            )
                        )
                        regex_count += 1
            span.set_attribute("pii.regex_entities_found", regex_count)
            trace_log.append({"step": "Regex Layer", "status": "Success", "details": f"Matched {regex_count} patterns."})

        detected.extend(self.detect_quasi_identifiers(text))
        trace_log.append(
            {
                "step": "Risk Assessment",
                "status": "Success",
                "time_ms": int((time.time() - t0) * 1000),
                "details": f"Final Entity Count: {len(detected)}",
            }
        )
        return detected


detection_engine = DetectionEngine()


class PolicySyncAgent:
    def __init__(self):
        # tenant_id -> {"policy": {...}, "expires_at": float}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock_for(self, tenant_id: str) -> asyncio.Lock:
        if tenant_id not in self._locks:
            self._locks[tenant_id] = asyncio.Lock()
        return self._locks[tenant_id]

    async def get_policy_for_tenant(self, tenant_id: str, auth_header: Optional[str]) -> Dict[str, Any]:
        tenant_key = tenant_id.strip()
        if not tenant_key:
            raise HTTPException(400, "tenant_id is required")
        now = time.time()
        cached = self._cache.get(tenant_key)
        if cached and cached.get("expires_at", 0) > now:
            return cached["policy"]

        lock = self._lock_for(tenant_key)
        async with lock:
            now = time.time()
            cached = self._cache.get(tenant_key)
            if cached and cached.get("expires_at", 0) > now:
                return cached["policy"]

            try:
                policy = await self._fetch_policy_from_policy_service(tenant_key, auth_header)
                self._cache[tenant_key] = {
                    "policy": policy,
                    "expires_at": now + max(1, POLICY_CACHE_TTL_SECONDS),
                }
                return policy
            except HTTPException:
                if cached and cached.get("expires_at", 0) + max(0, POLICY_CACHE_STALE_GRACE_SECONDS) > now:
                    # Prefer stale policy over hard failure for resilience.
                    return cached["policy"]
                raise

    async def _fetch_policy_from_policy_service(self, tenant_id: str, auth_header: Optional[str]) -> Dict[str, Any]:
        headers: Dict[str, str] = {"accept": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        base = POLICY_SERVICE_BASE_URL.rstrip("/")
        url = f"{base}/api/v1/policy-service/policies"

        page = 1
        limit = 20
        collected: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=POLICY_SERVICE_TIMEOUT) as client:
            while True:
                params = {
                    "tenant_id": tenant_id,
                    "is_active": "true",
                    "page": page,
                    "limit": limit,
                }
                try:
                    response = await client.get(url, params=params, headers=headers)
                except httpx.TimeoutException:
                    raise HTTPException(502, "Policy Service request timed out")
                except httpx.RequestError as exc:
                    raise HTTPException(502, f"Policy Service unavailable: {type(exc).__name__}")

                if response.status_code == 401:
                    raise HTTPException(401, "Unauthorized to fetch policies from Policy Service")
                if response.status_code == 403:
                    raise HTTPException(403, "Forbidden while fetching policies from Policy Service")
                if response.status_code >= 400:
                    raise HTTPException(502, f"Policy Service error: status {response.status_code}")

                payload = response.json() or {}
                rows = payload.get("data") or []
                if isinstance(rows, list):
                    collected.extend(rows)

                meta = payload.get("meta") or {}
                total = int(meta.get("total", len(collected) or 0))
                if len(collected) >= total or not rows:
                    break
                page += 1

        active_policies = [p for p in collected if p.get("is_active", True)]
        if not active_policies:
            raise HTTPException(404, f"No active policy found for tenant '{tenant_id}'")
        adapted = self._adapt_policy_response(active_policies[0], tenant_id)
        return adapted

    def _adapt_policy_response(self, policy: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        rules: List[Dict[str, Any]] = []
        pii_types = policy.get("pii_types") or []
        for pii in pii_types:
            entity_label = (
                pii.get("pii_type_label")
                or pii.get("entity_type")
                or pii.get("label")
            )
            if not entity_label:
                continue
            mask_format = str(pii.get("mask_format", "redact")).lower()
            if mask_format == "full":
                action = "MASK"
                config: Dict[str, Any] = {"mask_char": "X"}
            elif mask_format == "partial":
                action = "REDACT_TAG"
                config = {"tag_label": f"[{entity_label}]"}
            else:
                action = "REDACT_TAG"
                config = {"tag_label": "[REDACTED]"}

            # Support optional regex fields when policy service includes them.
            custom_regex = pii.get("regex_pattern") or pii.get("regex") or None
            rule = {
                "entity_type": str(entity_label).upper(),
                "action": action,
                "config": config,
            }
            if custom_regex:
                rule["custom_regex"] = custom_regex
            rules.append(rule)

        if not rules:
            raise HTTPException(
                422,
                f"Policy '{policy.get('name')}' for tenant '{tenant_id}' does not contain usable PII rules",
            )

        return {
            "meta": {
                "tenant_id": tenant_id,
                "policy_id": policy.get("policy_id"),
                "policy_name": policy.get("name"),
            },
            "rules": rules,
        }


policy_agent = PolicySyncAgent()


class AuditLogger:
    async def log_event(self, trace_id, tenant_id, domain, target, pii_count, processing_ms, trace_log):
        global db_pool, kafka_producer
        payload = {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "domain_id": domain,
            "target_context": target,
            "pii_count": pii_count,
            "processing_ms": processing_ms,
            "trace_json": trace_log,
        }

        # Primary sink for admin UI: persist directly to audit_logs table.
        try:
            if db_pool:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO audit_logs (
                            trace_id,
                            tenant_id,
                            domain_id,
                            target_context,
                            pii_count,
                            processing_ms,
                            trace_json
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                        """,
                        trace_id,
                        tenant_id,
                        domain,
                        target,
                        pii_count,
                        processing_ms,
                        json.dumps(trace_log),
                    )
        except Exception as exc:
            print(f"Audit DB insert failed: {exc}")

        # Secondary sink: Kafka best-effort publish.
        if not kafka_producer:
            return
        try:
            await kafka_producer.send(
                KAFKA_AUDIT_TOPIC,
                json.dumps(payload).encode("utf-8"),
            )
        except Exception as exc:
            print(f"Kafka audit publish failed: {exc}")


audit_logger = AuditLogger()


class RedactionRequest(BaseModel):
    text: str = Field(..., max_length=20000)


@app.on_event("startup")
async def startup_event():
    global db_pool, kafka_producer
    for _ in range(10):
        try:
            db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST, min_size=3, max_size=20)
            break
        except Exception as exc:
            print(f"DB connection failed ({exc}), retrying...")
            await asyncio.sleep(3)
    if not db_pool:
        raise RuntimeError("Could not connect to PostgreSQL")

    try:
        kafka_producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await kafka_producer.start()
    except Exception as exc:
        print(f"Kafka connection failed: {exc}")

    await KB.refresh()


@app.on_event("shutdown")
async def shutdown_event():
    global db_pool, kafka_producer
    if db_pool:
        await db_pool.close()
    if kafka_producer:
        await kafka_producer.stop()


@app.get("/")
async def root():
    return JSONResponse({"service": "pii-guard", "status": "ok"})


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/redact")
async def redact_text(
    payload: RedactionRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    auth=Depends(AuthProvider),
    include_original_text: bool = Query(default=False),
    x_target: str = Header("user"),
    x_language: str = Header("en"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
):
    claims_tid = (getattr(auth, "tenant_id", None) or "").strip() if auth is not None else ""
    header_tid = (x_tenant_id or "").strip() or None
    if header_tid and header_tid != claims_tid:
        # Prevent tenant spoofing when token already carries tenant_id.
        if claims_tid:
            raise HTTPException(
                403,
                "X-Tenant-Id header does not match token tenant_id.",
            )
    tenant_id = claims_tid or header_tid
    if not tenant_id:
        raise HTTPException(400, "tenant_id is required in token or X-Tenant-Id header")
    start = time.time()
    span_ctx = trace.get_current_span().get_span_context()
    trace_id = f"{span_ctx.trace_id:032x}" if getattr(span_ctx, "is_valid", False) else ""
    trace_log = [{"step": "Request", "status": "Success", "details": f"Target: {x_target}, Lang: {x_language}"}]

    if not KB.connected:
        await KB.refresh()

    auth_header = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
    policy = await policy_agent.get_policy_for_tenant(tenant_id, auth_header)

    is_strict = x_target.lower() != "user"
    entities = await detection_engine.detect(payload.text, policy["rules"], trace_log, is_strict, x_language)
    entities.sort(key=lambda x: x.start_index)

    redacted = payload.text
    for ent in sorted(entities, key=lambda x: x.start_index, reverse=True):
        rule = next((r for r in policy["rules"] if r["entity_type"] == ent.entity_type), None)
        if not rule:
            continue
        rep = "[REDACTED]"
        if rule["action"] == "REDACT_TAG":
            rep = rule["config"].get("tag_label", f"[{ent.entity_type}]")
        elif rule["action"] == "MASK":
            char = rule["config"].get("mask_char", "X")
            rep = char * len(ent.text_segment)
        redacted = redacted[: ent.start_index] + rep + redacted[ent.end_index :]

    ms = int((time.time() - start) * 1000)
    background_tasks.add_task(
        audit_logger.log_event,
        trace_id,
        tenant_id,
        policy.get("meta", {}).get("policy_name"),
        x_target,
        len(entities),
        ms,
        trace_log,
    )
    response_payload = {
        "redacted_text": redacted,
        "pii_detected": entities,
        "trace": trace_log,
        "metadata": {
            "processing_time_ms": ms,
            "language": x_language,
            "policy_id": policy.get("meta", {}).get("policy_id"),
            "policy_name": policy.get("meta", {}).get("policy_name"),
            "tenant_id": tenant_id,
        },
    }
    if include_original_text:
        response_payload["original_text"] = payload.text
    return response_payload



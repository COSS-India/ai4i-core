from fastapi import FastAPI, HTTPException, Request, Header, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import re
import hashlib
import hmac
import os
import json
import time
import uuid
import asyncpg
import httpx
import redis.asyncio as aioredis
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
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
NER_SERVICE_URL = os.getenv("NER_SERVICE_URL", "http://localhost:9001/ner")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_AUDIT_TOPIC = os.getenv("KAFKA_AUDIT_TOPIC", "pii_audit_logs")
PII_HMAC_KEY = os.getenv("PII_HMAC_KEY", "change-me-in-production").encode("utf-8")

db_pool = None
redis_client = None
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
        self._cache = {}
        self._active_domain_ids: set = set()
        self._tenant_domain: Dict[str, str] = {}
        self.connected = False

    async def refresh_policies(self):
        global db_pool
        if not db_pool:
            return
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT domain_id, policy_json, is_active FROM domain_policies"
                )
                self._cache = {
                    row["domain_id"]: json.loads(row["policy_json"])
                    if isinstance(row["policy_json"], str)
                    else row["policy_json"]
                    for row in rows
                }
                self._active_domain_ids = {row["domain_id"] for row in rows if row["is_active"]}
                try:
                    trows = await conn.fetch(
                        "SELECT tenant_id, domain_id FROM tenant_pii_domain_map"
                    )
                    self._tenant_domain = {
                        row["tenant_id"]: row["domain_id"] for row in trows
                    }
                except Exception:
                    self._tenant_domain = {}
                self.connected = True
        except Exception as exc:
            print(f"Policy sync failed: {exc}")

    async def listen_for_updates(self):
        global redis_client
        if not redis_client:
            return
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("policy_updates")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await self.refresh_policies()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"Redis listen error: {exc}")

    async def get_policy(self, domain):
        if not self.connected:
            await self.refresh_policies()
        return self._cache.get(domain)

    async def list_domains(self):
        if not self.connected:
            await self.refresh_policies()
        return sorted(self._active_domain_ids)

    def resolve_domain_for_tenant(self, tenant_id: Optional[str]) -> Optional[str]:
        if not tenant_id:
            return None
        return self._tenant_domain.get(str(tenant_id).strip())


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


class TenantDomainUpsertRequest(BaseModel):
    tenant_id: str
    domain_id: str


class TenantDomainDeleteRequest(BaseModel):
    tenant_id: str


class DeployRequest(BaseModel):
    domain_id: str
    rules: List[Dict]


class BulkActivateRequest(BaseModel):
    domain_ids: List[str]


class GenerateRegexRequest(BaseModel):
    example_text: str


class NewDomainRequest(BaseModel):
    domain_id: str
    description: str


@app.on_event("startup")
async def startup_event():
    global db_pool, redis_client, kafka_producer
    for _ in range(10):
        try:
            db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST, min_size=3, max_size=20)
            break
        except Exception as exc:
            print(f"DB connection failed ({exc}), retrying...")
            await asyncio.sleep(3)
    if not db_pool:
        raise RuntimeError("Could not connect to PostgreSQL")

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.redis_client = redis_client
    asyncio.create_task(policy_agent.listen_for_updates())

    try:
        kafka_producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await kafka_producer.start()
    except Exception as exc:
        print(f"Kafka connection failed: {exc}")

    await KB.refresh()
    await policy_agent.refresh_policies()


@app.on_event("shutdown")
async def shutdown_event():
    global db_pool, redis_client, kafka_producer
    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.close()
    if kafka_producer:
        await kafka_producer.stop()


@app.get("/")
async def root():
    return JSONResponse({"service": "pii-guard", "status": "ok"})


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/domains")
async def get_domains(auth=Depends(AuthProvider)):
    _ = auth
    return await policy_agent.list_domains()


@app.get("/policy/{domain}")
async def get_policy(domain: str, auth=Depends(AuthProvider)):
    _ = auth
    return await policy_agent.get_policy(domain) or {}


def require_pii_admin(auth_claims):
    roles = [str(r).upper() for r in (getattr(auth_claims, "roles", []) or [])]
    if "ADMIN" not in roles and "TENANT ADMIN" not in roles:
        raise HTTPException(403, "Admin privileges required.")


@app.post("/redact")
async def redact_text(
    request: RedactionRequest,
    background_tasks: BackgroundTasks,
    auth=Depends(AuthProvider),
    include_original_text: bool = Query(default=False),
    x_target: str = Header("user"),
    x_language: str = Header("en"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
):
    claims_tid = getattr(auth, "tenant_id", None) if auth is not None else None
    header_tid = (x_tenant_id or "").strip() or None
    if header_tid and header_tid != claims_tid:
        # Prevent tenant spoofing when token already carries tenant_id.
        if claims_tid:
            raise HTTPException(
                403,
                "X-Tenant-Id header does not match token tenant_id.",
            )
    tenant_id = claims_tid
    start = time.time()
    trace_id = str(uuid.uuid4())
    trace_log = [{"step": "Request", "status": "Success", "details": f"Target: {x_target}, Lang: {x_language}"}]

    if not KB.connected:
        await KB.refresh()

    if not policy_agent.connected:
        await policy_agent.refresh_policies()
    effective_domain = policy_agent.resolve_domain_for_tenant(tenant_id)
    fallback_message: Optional[str] = None
    if not tenant_id:
        effective_domain = "logistics"
        fallback_message = (
            "Token has no tenant_id claim. Using 'logistics' as fallback. "
            "Map/authenticate with tenant context for tenant-specific redaction."
        )
        trace_log.append(
            {
                "step": "DomainResolution",
                "status": "Fallback",
                "details": "Token missing tenant_id. Using 'logistics'.",
            }
        )
    if not effective_domain:
        effective_domain = "logistics"
        fallback_message = (
            "No domain is mapped to this tenant. Using 'logistics' as fallback because it is comprehensive. "
            "Map the tenant to the appropriate domain for specific redaction behavior."
        )
        trace_log.append(
            {
                "step": "DomainResolution",
                "status": "Fallback",
                "details": f"Tenant '{tenant_id}' has no mapped domain. Using 'logistics'.",
            }
        )

    policy = await policy_agent.get_policy(effective_domain)
    if not policy:
        raise HTTPException(
            400,
            f"Unknown domain '{effective_domain}'. Create the domain or fix tenant_pii_domain_map.",
        )

    is_strict = x_target.lower() != "user"
    entities = await detection_engine.detect(request.text, policy["rules"], trace_log, is_strict, x_language)
    entities.sort(key=lambda x: x.start_index)

    redacted = request.text
    for ent in sorted(entities, key=lambda x: x.start_index, reverse=True):
        rule = next((r for r in policy["rules"] if r["entity_type"] == ent.entity_type), None)
        if not rule:
            continue
        rep = "[REDACTED]"
        if rule["action"] == "REDACT_TAG":
            rep = rule["config"].get("tag_label", f"[{ent.entity_type}]")
        elif rule["action"] == "HASH":
            rep = hmac.new(PII_HMAC_KEY, ent.text_segment.encode(), hashlib.sha256).hexdigest()[:10] + "..."
        elif rule["action"] == "MASK":
            char = rule["config"].get("mask_char", "X")
            rep = char * len(ent.text_segment)
        redacted = redacted[: ent.start_index] + rep + redacted[ent.end_index :]

    ms = int((time.time() - start) * 1000)
    background_tasks.add_task(
        audit_logger.log_event, trace_id, tenant_id, effective_domain, x_target, len(entities), ms, trace_log
    )
    response_payload = {
        "redacted_text": redacted,
        "pii_detected": entities,
        "trace": trace_log,
        "metadata": {
            "processing_time_ms": ms,
            "language": x_language,
            "domain": effective_domain,
            "tenant_id": tenant_id or "unknown",
            "message": fallback_message,
        },
    }
    if include_original_text:
        response_payload["original_text"] = request.text
    return response_payload


@app.get("/admin/all-domains")
async def get_all_domains(auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT domain_id, is_active, policy_json->'meta'->>'description' as description FROM domain_policies ORDER BY domain_id;"
        )
        return [dict(row) for row in rows]


@app.post("/admin/deploy")
async def deploy(req: DeployRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool, redis_client
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT policy_json FROM domain_policies WHERE domain_id = $1", req.domain_id)
        if not row:
            raise HTTPException(404, "Domain not found")
        policy = json.loads(row["policy_json"]) if isinstance(row["policy_json"], str) else row["policy_json"]
        policy["rules"] = req.rules
        await conn.execute("UPDATE domain_policies SET policy_json = $1 WHERE domain_id = $2", json.dumps(policy), req.domain_id)
    if redis_client:
        await redis_client.publish("policy_updates", "deployed")
    return {"status": "saved"}


@app.post("/admin/activate-domains")
async def activate(req: BulkActivateRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool, redis_client
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE domain_policies SET is_active = FALSE")
        if req.domain_ids:
            await conn.execute("UPDATE domain_policies SET is_active = TRUE WHERE domain_id = ANY($1)", req.domain_ids)
    if redis_client:
        await redis_client.publish("policy_updates", "activated")
    return {"status": "success"}


@app.post("/admin/generate-regex")
async def gen_regex(req: GenerateRegexRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    base_ip = NER_SERVICE_URL.split(":")[1].replace("//", "")
    llm_url = f"http://{base_ip}:8000/api/query"
    prompt = (
        f"Generate a general python regex pattern to EXTRACT data similar to this example: '{req.example_text}'. "
        "Use word boundaries (\\b). Return only the raw regex string."
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(llm_url, json={"query": prompt, "system_prompt": None, "context": None}, timeout=20.0)
            if response.status_code == 200:
                data = response.json()
                return {"regex": data.get("result", "").strip('`"\'\n ')}
            return {"regex": f"HTTP_ERROR_{response.status_code}"}
        except Exception as exc:
            return {"regex": f"LLM_ERROR: {exc}"}


@app.post("/admin/domain")
async def create_domain(req: NewDomainRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO domain_policies VALUES ($1, FALSE, $2)",
            req.domain_id,
            json.dumps({"meta": {"version": "1.0", "description": req.description}, "rules": []}),
        )
    return {"status": "success"}


@app.get("/admin/tenant-domains")
async def list_tenant_domain_mappings(auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tenant_id, domain_id, updated_at FROM tenant_pii_domain_map ORDER BY tenant_id"
        )
        return [dict(row) for row in rows]


@app.post("/admin/tenant-domain")
async def upsert_tenant_domain_mapping(req: TenantDomainUpsertRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool, redis_client
    tid, did = req.tenant_id.strip(), req.domain_id.strip()
    if not tid or not did:
        raise HTTPException(400, "tenant_id and domain_id are required")
    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow(
            "SELECT 1 FROM domain_policies WHERE domain_id = $1 LIMIT 1", did
        )
        if not exists:
            raise HTTPException(404, f"domain_id '{did}' not found in domain_policies")
        await conn.execute(
            """
            INSERT INTO tenant_pii_domain_map (tenant_id, domain_id, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id)
            DO UPDATE SET domain_id = EXCLUDED.domain_id, updated_at = CURRENT_TIMESTAMP
            """,
            tid,
            did,
        )
    if redis_client:
        await redis_client.publish("policy_updates", "tenant_map")
    await policy_agent.refresh_policies()
    return {"status": "success", "tenant_id": tid, "domain_id": did}


@app.post("/admin/tenant-domain/delete")
async def delete_tenant_domain_mapping(req: TenantDomainDeleteRequest, auth=Depends(AuthProvider)):
    require_pii_admin(auth)
    global db_pool, redis_client
    tid = req.tenant_id.strip()
    if not tid:
        raise HTTPException(400, "tenant_id is required")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tenant_pii_domain_map WHERE tenant_id = $1", tid)
    if redis_client:
        await redis_client.publish("policy_updates", "tenant_map")
    await policy_agent.refresh_policies()
    return {"status": "success"}


@app.get("/admin/audit-logs")
async def list_audit_logs(
    auth=Depends(AuthProvider),
    limit: int = Query(default=50, ge=1, le=500),
):
    require_pii_admin(auth)
    global db_pool
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, trace_id, tenant_id, domain_id, target_context, pii_count, processing_ms, trace_json, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]

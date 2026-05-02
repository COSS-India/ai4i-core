"""
Targeted tests for the three PII-related fixes:
  1. api_permissions.json no longer gates POST:/redact
  2. /redact endpoint uses OptionalAuthProvider (not AuthProvider)
  3. listen_for_updates calls KB.refresh() after policy reload
"""

import ast
import json
import asyncio
import sys
import os
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PII_MAIN = Path(__file__).parent / "main.py"
API_PERMS = REPO_ROOT / "services/auth-service-v2/api_permissions.json"


# ── Test 1: api_permissions.json ─────────────────────────────────────────────

def test_api_permissions_no_redact_entry():
    data = json.loads(API_PERMS.read_text())
    # The JSON may use different top-level keys — search all string values
    raw = API_PERMS.read_text()
    assert "POST:/redact" not in raw, (
        "POST:/redact still present in api_permissions.json — "
        "auth-service will restore permission 65 in Redis on startup"
    )
    print("PASS  api_permissions.json does not contain POST:/redact")


# ── Test 2: /redact uses OptionalAuthProvider ─────────────────────────────────

def test_redact_endpoint_uses_optional_auth():
    tree = ast.parse(PII_MAIN.read_text())

    redact_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "redact_text":
            redact_func = node
            break

    assert redact_func is not None, "redact_text function not found in main.py"

    # Inspect default values of the function arguments for Depends(OptionalAuthProvider)
    defaults = redact_func.args.defaults + redact_func.args.kw_defaults
    found_optional = False
    found_required = False
    for default in defaults:
        if default is None:
            continue
        src = ast.unparse(default)
        if "OptionalAuthProvider" in src:
            found_optional = True
        if src == "Depends(AuthProvider)":
            found_required = True

    assert found_optional, "redact_text does not use Depends(OptionalAuthProvider)"
    assert not found_required, "redact_text still uses Depends(AuthProvider) — must be Optional"
    print("PASS  /redact endpoint uses OptionalAuthProvider")


# ── Test 3: listen_for_updates calls KB.refresh() ────────────────────────────

def test_listen_for_updates_calls_kb_refresh():
    tree = ast.parse(PII_MAIN.read_text())

    # Find the PolicySyncAgent class → listen_for_updates method
    listen_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PolicySyncAgent":
            for item in ast.walk(node):
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "listen_for_updates":
                    listen_func = item
                    break

    assert listen_func is not None, "PolicySyncAgent.listen_for_updates not found"

    # Find all awaited calls in the function body
    awaited_calls = []
    for node in ast.walk(listen_func):
        if isinstance(node, ast.Await):
            awaited_calls.append(ast.unparse(node))

    has_kb_refresh = any("KB.refresh" in c for c in awaited_calls)
    has_policy_refresh = any("refresh_policies" in c for c in awaited_calls)

    assert has_kb_refresh, (
        f"listen_for_updates does not await KB.refresh(). Found awaits: {awaited_calls}"
    )
    assert has_policy_refresh, (
        "listen_for_updates does not await refresh_policies() — regression?"
    )
    print("PASS  listen_for_updates awaits both refresh_policies() and KB.refresh()")


# ── Test 4: KB.refresh loads patterns from DB (mock DB) ──────────────────────

def test_kb_refresh_populates_patterns():
    """
    Instantiate KnowledgeBase with a mock DB pool and verify it loads patterns
    into self.patterns keyed by lang_code.
    """
    # Patch all heavy imports before importing main
    # Stub aiokafka with required class
    aiokafka_mod = types.ModuleType("aiokafka")
    aiokafka_mod.AIOKafkaProducer = type("AIOKafkaProducer", (), {})
    sys.modules["aiokafka"] = aiokafka_mod

    # Stub opentelemetry sub-modules with required names
    otel_instrumentor_mod = types.ModuleType("opentelemetry.instrumentation.fastapi")
    otel_instrumentor_mod.FastAPIInstrumentor = type("FastAPIInstrumentor", (), {"instrument_app": lambda *a, **kw: None})
    sys.modules["opentelemetry.instrumentation.fastapi"] = otel_instrumentor_mod

    otel_trace_mod = types.ModuleType("opentelemetry.trace")
    otel_trace_mod.get_tracer = lambda *a, **kw: types.SimpleNamespace(start_as_current_span=lambda *a, **kw: __import__('contextlib').nullcontext())
    sys.modules["opentelemetry.trace"] = otel_trace_mod
    sys.modules["opentelemetry"] = types.SimpleNamespace(trace=otel_trace_mod)

    for mod in ["asyncpg", "redis", "redis.asyncio",
                "opentelemetry.sdk", "opentelemetry.sdk.trace",
                "opentelemetry.exporter.otlp",
                "opentelemetry.exporter.otlp.proto",
                "opentelemetry.exporter.otlp.proto.grpc",
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
                "ai4icore_exceptions", "ai4icore_env",
                "ai4icore_telemetry", "middleware.auth_provider"]:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    # Minimal stubs
    sys.modules["ai4icore_env"].app_env = types.SimpleNamespace(
        auth_enabled=False, debug=False, redis_url=None,
        jwks_url=None, auth_service_url=None, jwks_path=None,
        jwt_issuer=None, jwt_issuer_url=None, jwt_audience=None,
    )

    auth_mod = sys.modules["middleware.auth_provider"]

    class _FakeDep:
        pass

    auth_mod.AuthProvider = _FakeDep
    auth_mod.OptionalAuthProvider = _FakeDep

    exceptions_mod = sys.modules["ai4icore_exceptions"]
    exceptions_mod.register_exception_handlers = lambda app: None

    telemetry_mod = sys.modules["ai4icore_telemetry"] = types.ModuleType("ai4icore_telemetry")
    telemetry_mod.setup_tracing = lambda *a, **kw: None

    # Add the service directory to sys.path so relative imports work
    sys.path.insert(0, str(Path(__file__).parent))
    os.environ.setdefault("PII_HASH_KEY", "test-key")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_NAME", "test")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASS", "test")

    import importlib
    import main as pii_main

    KB = pii_main.KB

    # Inject a fake DB pool into the module-level global (KB.refresh uses `global db_pool`)
    fake_pattern_rows = [
        {"entity_label": "EMAIL", "lang_code": "all",
         "regex_pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"},
        {"entity_label": "PHONE", "lang_code": "all",
         "regex_pattern": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"},
        {"entity_label": "PERSON", "lang_code": "en",
         "regex_pattern": r"(?i)\b(?:Name|Mr\.|Ms\.|Mrs\.)\s+(?:is\s+)?[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"},
    ]
    fake_geo_rows = [
        {"term_text": "Road", "lang_code": "en", "term_type": "SUFFIX"},
        {"term_text": "Bangalore", "lang_code": "en", "term_type": "SAFE_CITY"},
    ]

    class FakeConn:
        async def fetch(self, query, *args):
            if "pattern_library" in query:
                return fake_pattern_rows
            return fake_geo_rows
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class FakePool:
        def acquire(self): return FakeConn()

    pii_main.db_pool = FakePool()

    asyncio.run(KB.refresh())

    # lang="all" patterns are expanded into en/hi/mr/ta, not stored under "all"
    assert "en" in KB.patterns, f"Expected 'en' in patterns, got: {list(KB.patterns.keys())}"
    assert "EMAIL" in KB.patterns["en"], "EMAIL pattern (from 'all') missing from 'en'"
    assert "PHONE" in KB.patterns["en"], "PHONE pattern (from 'all') missing from 'en'"
    assert "PERSON" in KB.patterns["en"], "PERSON pattern missing from 'en'"
    assert KB.safe_geo.get("en", set()) >= {"bangalore"}, "SAFE_CITY not loaded into safe_geo"
    assert "Road" in KB.suffixes.get("en", []), "SUFFIX not loaded into suffixes"
    print(f"PASS  KB.refresh() loaded patterns: { {k: list(v.keys()) for k, v in KB.patterns.items()} }")


def _get_pii_main():
    """Return already-imported pii main module (test 4 imports it first)."""
    import main as pii_main

    # Fix the tracer stub: nullcontext yields None, but detect() calls span.set_attribute().
    class _MockSpan:
        def set_attribute(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _MockTracer:
        def start_as_current_span(self, *a, **kw): return _MockSpan()

    pii_main.tracer = _MockTracer()

    # Also stub trace.get_current_span() used in the /redact endpoint
    _mock_span_ctx = types.SimpleNamespace(trace_id=0, is_valid=False)
    _mock_cur_span = types.SimpleNamespace(get_span_context=lambda: _mock_span_ctx)
    pii_main.trace = types.SimpleNamespace(
        get_current_span=lambda: _mock_cur_span,
        get_tracer=lambda *a, **kw: _MockTracer(),
    )

    return pii_main


def _seed_patterns_and_policy(pii_main):
    """Directly inject logistics patterns + policy into KB and policy_agent."""
    import re

    # Seed KB with the same patterns that are in pattern_library on staging
    PATTERNS = [
        ("EMAIL",        "all", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        ("PHONE",        "all", r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"),
        ("AADHAAR_UID",  "all", r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
        ("PAN_CARD",     "all", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        ("PERSON",       "en",  r"(?i)\b(?:Name|Mr\.|Ms\.|Mrs\.)\s+(?:is\s+)?[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"),
        ("HOUSE_ANCHOR", "en",  r"\b(?:Address|No\.|Flat|House|H\.No|Door|#|Plot|Tower|Wing|Floor|Villa|Apt)\s?[\w\d\-/.,]+\b"),
        ("TRACKING_ID",  "all", r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b"),
        ("COURIER_REF",  "all", r"\b1Z[0-9A-Z]{16}\b"),
    ]
    kb = pii_main.KB
    kb.patterns = {}
    kb.suffixes = {}
    kb.safe_geo = {}
    for label, lang, regex in PATTERNS:
        langs = ["en", "hi", "mr", "ta"] if lang == "all" else [lang]
        for l in langs:
            kb.patterns.setdefault(l, {})
            try:
                kb.patterns[l][label] = re.compile(regex, re.UNICODE | re.IGNORECASE)
            except re.error:
                pass
    kb.safe_geo["en"] = {"bangalore", "mumbai", "delhi", "chennai"}
    kb.suffixes["en"] = ["Road", "Street", "Nagar", "Colony"]
    kb.connected = True

    # Seed policy_agent with logistics domain (same rules as seeder)
    logistics_rules = [
        {"entity_type": "PERSON",       "action": "REDACT_TAG", "config": {"tag_label": "[NAME]"}},
        {"entity_type": "EMAIL",        "action": "REDACT_TAG", "config": {"tag_label": "[EMAIL]"}},
        {"entity_type": "PHONE",        "action": "HASH",       "config": {}},
        {"entity_type": "AADHAAR_UID",  "action": "REDACT_TAG", "config": {"tag_label": "[AADHAAR_UID]"}},
        {"entity_type": "PAN_CARD",     "action": "REDACT_TAG", "config": {"tag_label": "[PAN_CARD]"}},
        {"entity_type": "TRACKING_ID",  "action": "REDACT_TAG", "config": {"tag_label": "[TRACKING_ID]"}},
        {"entity_type": "COURIER_REF",  "action": "REDACT_TAG", "config": {"tag_label": "[COURIER_REF]"}},
        {"entity_type": "HOUSE_ANCHOR", "action": "REDACT_TAG", "config": {"tag_label": "[ADDRESS]"}},
        {"entity_type": "PIN_CODE",     "action": "MASK",       "config": {"mask_char": "X"}},
    ]
    pa = pii_main.policy_agent
    pa._cache = {
        "logistics": {
            "meta": {"version": "1.0", "description": "Logistics"},
            "rules": logistics_rules,
        }
    }
    pa._active_domain_ids = {"logistics"}
    pa._tenant_domain = {}
    pa.connected = True


# ── Test 5: Detection + redaction works end-to-end in-process ────────────────

def test_pii_detection_and_redaction():
    """
    Drive the detection engine + redaction logic directly (no HTTP, no DB).
    Confirms PII in NMT-like text is found and replaced correctly.
    """
    pii_main = _get_pii_main()
    _seed_patterns_and_policy(pii_main)

    # Texts that NMT would produce (source en, or translated back to en for test)
    cases = [
        (
            "My Name is Kashif Khan, please call me at 9876543210",
            ["PERSON", "PHONE"],
            ["Kashif Khan", "9876543210"],
        ),
        (
            "Send the parcel to Flat 3B, deliver to rahul@example.com",
            ["HOUSE_ANCHOR", "EMAIL"],
            ["Flat 3B", "rahul@example.com"],
        ),
        (
            "AWB: ABC1234567890, PAN ABCDE1234F",
            ["TRACKING_ID", "PAN_CARD"],
            ["ABC1234567890", "ABCDE1234F"],
        ),
    ]

    rules = pii_main.policy_agent._cache["logistics"]["rules"]

    for text, expected_types, expected_vals in cases:
        entities = asyncio.run(
            pii_main.detection_engine.detect(text, rules, [], False, "en")
        )
        found_types = {e.entity_type for e in entities}
        found_vals = [e.text_segment for e in entities]

        for et in expected_types:
            assert et in found_types, (
                f"Expected {et} in '{text}' but got: {found_types}\n"
                f"  (entities: {[(e.entity_type, e.text_segment) for e in entities]})"
            )

        # Run the same redaction logic the /redact endpoint runs
        import hmac as _hmac, hashlib as _hashlib
        redacted = text
        for ent in sorted(entities, key=lambda x: x.start_index, reverse=True):
            rule = next((r for r in rules if r["entity_type"] == ent.entity_type), None)
            if not rule:
                continue
            if rule["action"] == "REDACT_TAG":
                rep = rule["config"].get("tag_label", f"[{ent.entity_type}]")
            elif rule["action"] == "MASK":
                rep = rule["config"].get("mask_char", "X") * len(ent.text_segment)
            elif rule["action"] == "HASH":
                digest = _hmac.new(pii_main.PII_HASH_KEY, ent.text_segment.encode(), _hashlib.sha256).hexdigest()[:10]
                rep = f"{digest}..."
            else:
                rep = "[REDACTED]"
            redacted = redacted[: ent.start_index] + rep + redacted[ent.end_index :]

        for val in expected_vals:
            assert val not in redacted, (
                f"'{val}' was NOT redacted in output: '{redacted}'"
            )

        print(f"  {text!r}")
        print(f"  → {redacted!r}")

    print("PASS  PII detection + redaction correct for all test cases")


# ── Test 6: NMT _maybe_redact calls PII service and stores redacted text ──────

def test_nmt_maybe_redact_stores_redacted():
    """
    Simulate the NMT _maybe_redact path using a mock HTTP transport.
    Verifies: 200 → stores redacted text; 403 → silently stores raw (old broken behavior).
    """
    sys.path.insert(0, str(REPO_ROOT / "services/nmt-service"))

    import httpx

    # Patch the NMT pii_client import path
    nmt_pii_mod = types.ModuleType("app.clients.pii_client")
    # Import the real pii_client module from nmt-service
    real_pii_client_path = REPO_ROOT / "services/nmt-service/app/clients/pii_client.py"
    spec = __import__("importlib.util", fromlist=["spec_from_file_location", "module_from_spec"])
    import importlib.util
    spec = importlib.util.spec_from_file_location("pii_client_real", real_pii_client_path)
    pii_client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pii_client)

    redact_for_storage = pii_client.redact_for_storage
    pii_language_code = pii_client.pii_language_code

    # ── Scenario A: PII service returns 200 with redacted text ────────────────
    redacted_response = {"redacted_text": "My Name is [NAME], call me at abc12345ef..."}

    import json as _json

    def _make_200(request):
        return httpx.Response(200, content=_json.dumps(redacted_response).encode(), request=request)

    def _make_403(request):
        return httpx.Response(403, content=_json.dumps({"detail": "Missing permission: /redact.POST"}).encode(), request=request)

    async def run_200():
        client = httpx.AsyncClient(transport=httpx.MockTransport(_make_200))
        return await redact_for_storage(
            base_url="http://pii-service:8000",
            text="My Name is Kashif Khan, call me at 9876543210",
            lang="en",
            auth_headers=None,
            tenant_id="alerting-staging-f2f290",
            timeout=5.0,
            client=client,
        )

    async def run_403():
        client = httpx.AsyncClient(transport=httpx.MockTransport(_make_403))
        try:
            return await redact_for_storage(
                base_url="http://pii-service:8000",
                text="My Name is Kashif Khan",
                lang="en",
                auth_headers=None,
                tenant_id="alerting-staging-f2f290",
                timeout=5.0,
                client=client,
            )
        except Exception:
            return None  # Expected — NMT catches this and stores raw

    # Test 200 path
    result_200 = asyncio.run(run_200())
    assert result_200 == redacted_response["redacted_text"], (
        f"Expected redacted text, got: {result_200!r}"
    )
    assert "Kashif" not in result_200, "Name was not redacted in 200 response"
    print(f"  200 path: stored '{result_200}'")
    print("PASS  NMT _maybe_redact: 200 response stores redacted text")

    # Test 403 path (proves old behavior was broken — NMT silently stores raw)
    result_403 = asyncio.run(run_403())
    assert result_403 is None, "403 should raise HTTPStatusError, not return text"
    print("PASS  NMT _maybe_redact: 403 raises exception (NMT catches it → was storing raw — now fixed)")


if __name__ == "__main__":
    failures = []
    for name, fn in [
        ("api_permissions.json check", test_api_permissions_no_redact_entry),
        ("/redact OptionalAuthProvider check", test_redact_endpoint_uses_optional_auth),
        ("listen_for_updates KB.refresh check", test_listen_for_updates_calls_kb_refresh),
        ("KB.refresh pattern loading", test_kb_refresh_populates_patterns),
        ("PII detection + redaction", test_pii_detection_and_redaction),
        ("NMT _maybe_redact flow", test_nmt_maybe_redact_stores_redacted),
    ]:
        try:
            fn()
        except Exception as e:
            import traceback
            print(f"FAIL  {name}: {e}")
            traceback.print_exc()
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} test(s) failed: {failures}")
        sys.exit(1)
    else:
        print("\nAll tests passed.")

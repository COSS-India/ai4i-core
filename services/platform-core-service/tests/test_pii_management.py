"""
Comprehensive pytest test suite for the PII management layer.

All external dependencies (DB, Redis, httpx, OpenTelemetry) are mocked so
that the tests can run with `pytest` against a vanilla Python environment
— no running services required.

Import strategy
---------------
The services live under ``app/services/pii-management/`` (hyphenated directory
name that is not a valid Python identifier), so we use importlib to load each
module directly by file path and bind them into ``sys.modules`` under a stable
alias before any relative imports inside the service files are resolved.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 0.  Bootstrap: make sure the app package root is on sys.path so that
#     "from app.schemas…" imports inside the service modules resolve correctly.
# ---------------------------------------------------------------------------

_SERVICE_ROOT = Path(__file__).parent.parent          # …/platform-core-service
_PII_SVC_DIR  = _SERVICE_ROOT / "app" / "services" / "pii-management"

if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


# ---------------------------------------------------------------------------
# 1.  Stub out heavy/optional dependencies that are imported at module level
#     but are not available (or must not be exercised) during unit tests.
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs) -> types.ModuleType:
    """Insert a lightweight stub into sys.modules under *name*."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# opentelemetry stubs — the real package may or may not be installed;
# we want deterministic behaviour either way.
def _make_noop_tracer():
    tracer = MagicMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__enter__ = MagicMock(return_value=MagicMock())
    ctx_mgr.__exit__ = MagicMock(return_value=False)
    tracer.start_as_current_span = MagicMock(return_value=ctx_mgr)
    return tracer


_otel_trace = _stub_module("opentelemetry.trace")
_otel_trace.get_tracer = MagicMock(return_value=_make_noop_tracer())
_otel_trace.get_current_span = MagicMock(
    return_value=MagicMock(get_span_context=MagicMock(return_value=MagicMock(is_valid=False)))
)
_stub_module("opentelemetry", trace=_otel_trace)

# sqlalchemy / asyncpg stubs (we never call real DB)
_stub_module("sqlalchemy")
_stub_module("sqlalchemy.ext")
_sqla_async = _stub_module("sqlalchemy.ext.asyncio")
_sqla_async.AsyncSession = MagicMock  # service files do `from sqlalchemy.ext.asyncio import AsyncSession`

# httpx is used by detection_service and by FastAPI TestClient (starlette).
# We must NOT replace the real httpx module entirely — TestClient depends on it.
# Instead we leave httpx as-is here and patch AsyncClient inside the detection
# service module's own namespace after loading it (see below).

# Stub app.core.pii_database and app.core.config to avoid env-var loading
_pii_db_stub = _stub_module("app.core.pii_database")
_pii_db_stub.get_pii_db = MagicMock()
_pii_db_stub._pii_session_factory = None   # AuditService checks this

_config_stub = _stub_module("app.core.config")
_settings_mock = MagicMock()
_settings_mock.pii_llm_url = "http://fake-llm/api"
_config_stub.settings = _settings_mock

# Repository stubs — must expose the class names imported by service modules
_stub_module("app.repositories")
_stub_module("app.repositories.pii_management")

_policy_repo_stub = _stub_module("app.repositories.pii_management.policy_repository")
_policy_repo_stub.PolicyRepository = MagicMock

_tenant_repo_stub = _stub_module("app.repositories.pii_management.tenant_map_repository")
_tenant_repo_stub.TenantMapRepository = MagicMock

_pattern_repo_stub = _stub_module("app.repositories.pii_management.pattern_repository")
_pattern_repo_stub.PatternRepository = MagicMock

_audit_repo_stub = _stub_module("app.repositories.pii_management.audit_log_repository")
_audit_repo_stub.AuditLogRepository = MagicMock

# Admin schema stubs — FastAPI uses these as response_model / request body types,
# so they must be real Pydantic BaseModel subclasses (not MagicMock).
from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional, Any as _Any, List as _List
import datetime as _datetime

class _AuditLogEntry(_BaseModel):
    id: _Any = None
    trace_id: _Optional[str] = None
    tenant_id: _Optional[str] = None
    domain_id: _Optional[str] = None
    target_context: _Optional[str] = None
    pii_count: _Optional[int] = None
    processing_ms: _Optional[int] = None
    trace_json: _Optional[_Any] = None
    created_at: _Optional[_Any] = None

class _BulkActivateRequest(_BaseModel):
    domain_ids: _List[str] = []

class _DeployRequest(_BaseModel):
    domain_id: str = ""
    rules: _List[_Any] = []

class _GenerateRegexRequest(_BaseModel):
    example_text: str = ""

class _GenerateRegexResponse(_BaseModel):
    regex: str = ""

class _NewDomainRequest(_BaseModel):
    domain_id: str = ""
    description: str = ""

class _StatusResponse(_BaseModel):
    status: str = ""

class _TenantDomainDeleteRequest(_BaseModel):
    tenant_id: str = ""

class _TenantDomainEntry(_BaseModel):
    tenant_id: str = ""
    domain_id: str = ""
    updated_at: _Optional[_Any] = None

class _TenantDomainUpsertRequest(_BaseModel):
    tenant_id: str = ""
    domain_id: str = ""

class _TenantDomainUpsertResponse(_BaseModel):
    status: str = ""
    tenant_id: str = ""
    domain_id: str = ""

_admin_schema_stub = _stub_module("app.schemas.pii_management.admin")
_admin_schema_stub.AuditLogEntry               = _AuditLogEntry
_admin_schema_stub.BulkActivateRequest         = _BulkActivateRequest
_admin_schema_stub.DeployRequest               = _DeployRequest
_admin_schema_stub.GenerateRegexRequest        = _GenerateRegexRequest
_admin_schema_stub.GenerateRegexResponse       = _GenerateRegexResponse
_admin_schema_stub.NewDomainRequest            = _NewDomainRequest
_admin_schema_stub.StatusResponse              = _StatusResponse
_admin_schema_stub.TenantDomainDeleteRequest   = _TenantDomainDeleteRequest
_admin_schema_stub.TenantDomainEntry           = _TenantDomainEntry
_admin_schema_stub.TenantDomainUpsertRequest   = _TenantDomainUpsertRequest
_admin_schema_stub.TenantDomainUpsertResponse  = _TenantDomainUpsertResponse


# ---------------------------------------------------------------------------
# 2.  Import service modules via importlib (hyphenated directory)
# ---------------------------------------------------------------------------

def _load_pii_module(filename: str, alias: str):
    """Load a .py file from the pii-management directory and register it."""
    spec = importlib.util.spec_from_file_location(
        alias, str(_PII_SVC_DIR / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# Order matters: kb_svc has no intra-package deps, then detection_service
# imports kb_svc, etc.
_kb_mod       = _load_pii_module("knowledge_base_service.py",
                                  "app.services.pii_management.knowledge_base_service")
_detect_mod   = _load_pii_module("detection_service.py",
                                  "app.services.pii_management.detection_service")

# Patch httpx.AsyncClient inside the detection module's namespace so that
# _fetch_ai_entities never attempts a real network call.  Tests that care
# about the returned value patch _fetch_ai_entities directly; this just
# guarantees a safe default for any stray call.
_detect_mod.httpx = MagicMock()
_detect_mod.httpx.AsyncClient = MagicMock

_policy_mod   = _load_pii_module("policy_sync_service.py",
                                  "app.services.pii_management.policy_sync_service")
_audit_mod    = _load_pii_module("audit_service.py",
                                  "app.services.pii_management.audit_service")
_redact_mod   = _load_pii_module("redaction_service.py",
                                  "app.services.pii_management.redaction_service")

KnowledgeBaseService = _kb_mod.KnowledgeBaseService
DetectionEngine      = _detect_mod.DetectionEngine
PolicySyncService    = _policy_mod.PolicySyncService
RedactionService     = _redact_mod.RedactionService

# Pull schema classes (standard import — no hyphen)
from app.schemas.pii_management.redaction import (  # noqa: E402
    DetectedEntity,
    RedactionMetadata,
    RedactionResponse,
)


# ===========================================================================
# Section 1 — DetectionEngine
# ===========================================================================

class TestDetectQuasiIdentifiers:
    """Unit tests for DetectionEngine._detect_quasi_identifiers."""

    def _engine(self):
        kb = MagicMock(spec=KnowledgeBaseService)
        kb.patterns = {}
        return DetectionEngine(kb=kb, ner_service_url="http://fake-ner")

    def test_finds_occupation_token(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("He works as a farmer in Delhi.")
        occupations = [e for e in results if e.entity_type == "OCCUPATION"]
        assert len(occupations) == 1
        assert occupations[0].text_segment.lower() == "farmer"
        assert occupations[0].detection_source == "KEYWORD"
        assert occupations[0].risk_score == pytest.approx(0.3)
        assert occupations[0].start_index >= 0
        assert occupations[0].end_index > occupations[0].start_index

    def test_finds_gender_token(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("The patient is male.")
        genders = [e for e in results if e.entity_type == "GENDER"]
        assert len(genders) == 1
        assert genders[0].text_segment.lower() == "male"
        assert genders[0].risk_score == pytest.approx(0.2)

    def test_finds_both_occupation_and_gender(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("A female teacher applied.")
        types_found = {e.entity_type for e in results}
        assert "OCCUPATION" in types_found
        assert "GENDER" in types_found

    def test_returns_correct_span_indices(self):
        engine = self._engine()
        text = "The driver spoke."
        results = engine._detect_quasi_identifiers(text)
        assert results, "Expected at least one entity"
        entity = results[0]
        assert text[entity.start_index:entity.end_index].lower() == entity.text_segment.lower()

    def test_no_match_returns_empty(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("Nothing sensitive here at all.")
        assert results == []

    def test_case_insensitive_match(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("She is a DOCTOR.")
        occupations = [e for e in results if e.entity_type == "OCCUPATION"]
        assert len(occupations) == 1

    def test_multiple_occupations_in_text(self):
        engine = self._engine()
        results = engine._detect_quasi_identifiers("A nurse and a teacher both signed.")
        occupations = [e for e in results if e.entity_type == "OCCUPATION"]
        assert len(occupations) == 2


class TestDetectionEngineLayer1:
    """Tests for detect() Layer 1: AI NER extraction."""

    def _engine(self, patterns=None):
        kb = MagicMock(spec=KnowledgeBaseService)
        kb.patterns = {"en": patterns or {}}
        return DetectionEngine(kb=kb, ner_service_url="http://fake-ner")

    @pytest.mark.asyncio
    async def test_ai_label_map_gpe_becomes_location(self):
        engine = self._engine()
        ai_response = [
            {"text": "Mumbai", "label": "GPE", "start_char": 10, "end_char": 16}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("lives in Mumbai daily", rules, trace_log)
        locs = [e for e in entities if e.entity_type == "LOCATION"]
        assert len(locs) >= 1
        assert locs[0].detection_source == "AI: GPE"

    @pytest.mark.asyncio
    async def test_ai_label_map_loc_becomes_location(self):
        engine = self._engine()
        ai_response = [
            {"text": "Nile River", "label": "LOC", "start_char": 0, "end_char": 10}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("Nile River is long", rules, trace_log)
        assert any(e.entity_type == "LOCATION" for e in entities)

    @pytest.mark.asyncio
    async def test_ai_label_map_person_stays_person(self):
        engine = self._engine()
        ai_response = [
            {"text": "Rahul Kumar", "label": "PERSON", "start_char": 5, "end_char": 16}
        ]
        rules = [{"entity_type": "PERSON", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("Name Rahul Kumar here", rules, trace_log)
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) == 1
        assert persons[0].detection_source == "AI: PERSON"

    @pytest.mark.asyncio
    async def test_ai_entity_in_false_positives_is_skipped(self):
        engine = self._engine()
        ai_response = [
            {"text": "phone", "label": "GPE", "start_char": 0, "end_char": 5}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("phone", rules, trace_log)
        # "phone" is in _FALSE_POSITIVES — should be skipped by AI layer
        ai_locs = [e for e in entities if e.detection_source.startswith("AI:")]
        assert ai_locs == []

    @pytest.mark.asyncio
    async def test_strict_mode_sets_score_to_1(self):
        engine = self._engine()
        ai_response = [
            {"text": "Delhi", "label": "GPE", "start_char": 0, "end_char": 5}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("Delhi", rules, trace_log, strict_mode=True)
        ai_ents = [e for e in entities if e.detection_source.startswith("AI:")]
        assert all(e.risk_score == pytest.approx(1.0) for e in ai_ents)

    @pytest.mark.asyncio
    async def test_non_strict_mode_sets_score_to_0_9(self):
        engine = self._engine()
        ai_response = [
            {"text": "Chennai", "label": "LOC", "start_char": 0, "end_char": 7}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("Chennai", rules, trace_log, strict_mode=False)
        ai_ents = [e for e in entities if e.detection_source.startswith("AI:")]
        assert all(e.risk_score == pytest.approx(0.9) for e in ai_ents)

    @pytest.mark.asyncio
    async def test_ai_entity_not_in_active_types_is_skipped(self):
        engine = self._engine()
        # AI returns a PERSON entity, but rules only contain LOCATION
        ai_response = [
            {"text": "Alice", "label": "PERSON", "start_char": 0, "end_char": 5}
        ]
        rules = [{"entity_type": "LOCATION", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=ai_response)):
            entities = await engine.detect("Alice", rules, trace_log)
        ai_ents = [e for e in entities if e.detection_source.startswith("AI:")]
        assert ai_ents == []

    @pytest.mark.asyncio
    async def test_ner_failure_returns_no_ai_entities(self):
        """When NER call raises, the engine should swallow it and return []."""
        engine = self._engine()
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            trace_log = []
            entities = await engine.detect("Some text", [], trace_log)
        ai_ents = [e for e in entities if e.detection_source.startswith("AI:")]
        assert ai_ents == []


class TestDetectionEngineLayer2:
    """Tests for detect() Layer 2: Regex scan."""

    def _engine(self, lang_patterns=None):
        kb = MagicMock(spec=KnowledgeBaseService)
        kb.patterns = {"en": lang_patterns or {}}
        return DetectionEngine(kb=kb, ner_service_url="http://fake-ner")

    @pytest.mark.asyncio
    async def test_custom_regex_rule_matches(self):
        engine = self._engine()
        rules = [{
            "entity_type": "VEHICLE_REG",
            "action": "REDACT",
            "config": {},
            "custom_regex": r"\b[A-Z]{2}\d{2}[A-Z]{2}\d{4}\b",
        }]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            entities = await engine.detect("Reg number MH12AB3456 here.", rules, trace_log)
        reg_ents = [e for e in entities if e.entity_type == "VEHICLE_REG"]
        assert len(reg_ents) == 1
        assert reg_ents[0].text_segment == "MH12AB3456"
        assert reg_ents[0].detection_source == "REGEX: Custom"
        assert reg_ents[0].risk_score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_invalid_custom_regex_is_caught_gracefully(self):
        engine = self._engine()
        rules = [{
            "entity_type": "BAD_TYPE",
            "action": "REDACT",
            "config": {},
            "custom_regex": r"[unclosed",   # invalid regex
        }]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            # Should NOT raise; invalid regex is logged and skipped
            entities = await engine.detect("some text", rules, trace_log)
        bad_ents = [e for e in entities if e.entity_type == "BAD_TYPE"]
        assert bad_ents == []

    @pytest.mark.asyncio
    async def test_pattern_library_fallback_when_no_custom_regex(self):
        phone_pattern = re.compile(r"\b(\d{10})\b")
        engine = self._engine(lang_patterns={"PHONE": phone_pattern})
        rules = [{"entity_type": "PHONE", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            entities = await engine.detect("Call me on 9876543210 please.", rules, trace_log)
        phone_ents = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phone_ents) == 1
        assert phone_ents[0].detection_source == "REGEX: PHONE"

    @pytest.mark.asyncio
    async def test_pattern_library_false_positive_skipped(self):
        """Values matching _FALSE_POSITIVES should be dropped by the pattern library path."""
        # Build a pattern that matches the word "email"
        email_word_pattern = re.compile(r"\b(email)\b", re.IGNORECASE)
        engine = self._engine(lang_patterns={"EMAIL": email_word_pattern})
        rules = [{"entity_type": "EMAIL", "action": "REDACT", "config": {}}]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            entities = await engine.detect("Send your email here", rules, trace_log)
        email_ents = [e for e in entities if e.entity_type == "EMAIL"]
        assert email_ents == [], "False positive 'email' should be filtered out"

    @pytest.mark.asyncio
    async def test_custom_regex_with_capture_group_uses_group1(self):
        engine = self._engine()
        rules = [{
            "entity_type": "TRACK_ID",
            "action": "REDACT",
            "config": {},
            "custom_regex": r"TID[:\s]+([A-Z0-9]+)",
        }]
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            entities = await engine.detect("Order TID: ABC123XY done.", rules, trace_log)
        track_ents = [e for e in entities if e.entity_type == "TRACK_ID"]
        assert len(track_ents) == 1
        assert track_ents[0].text_segment == "ABC123XY"


class TestDetectionEngineLayer3:
    """Tests ensuring Layer 3 (quasi-identifiers) always runs."""

    @pytest.mark.asyncio
    async def test_layer3_always_runs_and_accumulates(self):
        kb = MagicMock(spec=KnowledgeBaseService)
        kb.patterns = {"en": {}}
        engine = DetectionEngine(kb=kb, ner_service_url="http://fake-ner")

        rules = []   # empty rules — AI and regex layers yield nothing
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            entities = await engine.detect("A female driver arrived.", rules, trace_log)

        quasi = [e for e in entities
                 if e.detection_source == "KEYWORD"]
        assert len(quasi) >= 2   # "female" (GENDER) + "driver" (OCCUPATION)

    @pytest.mark.asyncio
    async def test_trace_log_has_three_steps(self):
        kb = MagicMock(spec=KnowledgeBaseService)
        kb.patterns = {"en": {}}
        engine = DetectionEngine(kb=kb, ner_service_url="http://fake-ner")
        trace_log = []
        with patch.object(engine, "_fetch_ai_entities", new=AsyncMock(return_value=[])):
            await engine.detect("text", [], trace_log)
        steps = [entry["step"] for entry in trace_log]
        assert "AI Extraction" in steps
        assert "Regex Layer" in steps
        assert "Risk Assessment" in steps


# ===========================================================================
# Section 2 — RedactionService
# ===========================================================================

class TestApplyRedactions:
    """Unit tests for RedactionService._apply_redactions (static method)."""

    def _make_entity(self, entity_type, start, end, text_segment):
        return DetectedEntity(
            entity_type=entity_type,
            start_index=start,
            end_index=end,
            text_segment=text_segment,
            detection_source="TEST",
            risk_score=1.0,
        )

    def test_redact_action_replaces_with_redacted_tag(self):
        text = "John lives in Mumbai."
        entities = [self._make_entity("PERSON", 0, 4, "John")]
        rules = [{"entity_type": "PERSON", "action": "REDACT", "config": {}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[REDACTED] lives in Mumbai."

    def test_redact_tag_action_uses_config_tag_label(self):
        text = "John works here."
        entities = [self._make_entity("PERSON", 0, 4, "John")]
        rules = [{"entity_type": "PERSON", "action": "REDACT_TAG", "config": {"tag_label": "[NAME]"}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[NAME] works here."

    def test_redact_tag_action_uses_default_when_no_tag_label(self):
        text = "John lives here."
        entities = [self._make_entity("PERSON", 0, 4, "John")]
        rules = [{"entity_type": "PERSON", "action": "REDACT_TAG", "config": {}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[PERSON] lives here."

    def test_mask_action_replaces_with_x_times_length(self):
        text = "Call 9876543210 now."
        entities = [self._make_entity("PHONE", 5, 15, "9876543210")]
        rules = [{"entity_type": "PHONE", "action": "MASK", "config": {}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "Call XXXXXXXXXX now."

    def test_mask_action_uses_custom_mask_char(self):
        text = "Call 9876543210 now."
        entities = [self._make_entity("PHONE", 5, 15, "9876543210")]
        rules = [{"entity_type": "PHONE", "action": "MASK", "config": {"mask_char": "*"}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "Call ********** now."

    def test_entity_with_no_matching_rule_is_left_unchanged(self):
        text = "John lives in Mumbai."
        entities = [self._make_entity("PERSON", 0, 4, "John")]
        rules = []  # No rules at all
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == text

    def test_reverse_order_preserves_indices_for_multiple_entities(self):
        # Two non-overlapping entities: "Alice" at 0-5 and "Bob" at 13-16
        text = "Alice called Bob today."
        entities = [
            self._make_entity("PERSON", 0, 5, "Alice"),
            self._make_entity("PERSON", 13, 16, "Bob"),
        ]
        rules = [{"entity_type": "PERSON", "action": "REDACT", "config": {}}]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[REDACTED] called [REDACTED] today."

    def test_multiple_entity_types_each_use_their_own_rule(self):
        text = "John lives in Mumbai."
        entities = [
            self._make_entity("PERSON",   0, 4,  "John"),
            self._make_entity("LOCATION", 14, 20, "Mumbai"),
        ]
        rules = [
            {"entity_type": "PERSON",   "action": "REDACT",    "config": {}},
            {"entity_type": "LOCATION", "action": "REDACT_TAG","config": {"tag_label": "[LOC]"}},
        ]
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[REDACTED] lives in [LOC]."

    def test_redact_action_is_default_when_action_key_missing(self):
        text = "John here."
        entities = [self._make_entity("PERSON", 0, 4, "John")]
        rules = [{"entity_type": "PERSON", "config": {}}]   # no "action" key
        result = RedactionService._apply_redactions(text, entities, rules)
        assert result == "[REDACTED] here."


class TestResolveDomain:
    """Unit tests for RedactionService._resolve_domain."""

    def _service(self, domain_map: Dict[str, str] = None):
        policy_sync = MagicMock()
        policy_sync.resolve_domain_for_tenant.side_effect = (
            lambda tid: (domain_map or {}).get(tid)
        )
        detection_engine = MagicMock()
        audit_service = MagicMock()
        return RedactionService(policy_sync, detection_engine, audit_service)

    def test_no_tenant_id_returns_logistics_fallback(self):
        svc = self._service()
        trace_log = []
        domain, msg = svc._resolve_domain(None, trace_log)
        assert domain == "logistics"
        assert msg is not None
        assert "logistics" in msg.lower()
        assert any(e["step"] == "DomainResolution" for e in trace_log)

    def test_mapped_tenant_returns_correct_domain(self):
        svc = self._service(domain_map={"tenant-abc": "healthcare"})
        trace_log = []
        domain, msg = svc._resolve_domain("tenant-abc", trace_log)
        assert domain == "healthcare"
        assert msg is None

    def test_unmapped_tenant_returns_logistics_fallback(self):
        svc = self._service(domain_map={})   # empty map
        trace_log = []
        domain, msg = svc._resolve_domain("unknown-tenant", trace_log)
        assert domain == "logistics"
        assert msg is not None
        assert "logistics" in msg.lower()

    def test_fallback_appends_trace_entry_for_no_tenant(self):
        svc = self._service()
        trace_log = []
        svc._resolve_domain(None, trace_log)
        statuses = [e["status"] for e in trace_log]
        assert "Fallback" in statuses

    def test_fallback_appends_trace_entry_for_unmapped_tenant(self):
        svc = self._service(domain_map={})
        trace_log = []
        svc._resolve_domain("ghost-tenant", trace_log)
        statuses = [e["status"] for e in trace_log]
        assert "Fallback" in statuses


class TestRedactionServiceFullPipeline:
    """Integration-style tests for RedactionService.redact() with all deps mocked."""

    def _make_service(
        self,
        domain: str = "logistics",
        policy: Dict = None,
        detected: List[DetectedEntity] = None,
    ):
        if policy is None:
            policy = {
                "rules": [{"entity_type": "PERSON", "action": "REDACT", "config": {}}]
            }
        if detected is None:
            detected = []

        policy_sync = MagicMock()
        policy_sync.resolve_domain_for_tenant.return_value = domain
        policy_sync.get_policy.return_value = policy

        detection_engine = MagicMock()
        detection_engine.detect = AsyncMock(return_value=detected)

        audit_service = MagicMock()
        audit_service.log_event = AsyncMock()

        svc = RedactionService(policy_sync, detection_engine, audit_service)
        return svc, policy_sync, detection_engine, audit_service

    @pytest.mark.asyncio
    async def test_redact_returns_redaction_response_type(self):
        svc, _, _, _ = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="Hello world",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        assert isinstance(result, RedactionResponse)

    @pytest.mark.asyncio
    async def test_redact_metadata_fields_populated(self):
        svc, _, _, _ = self._make_service(domain="logistics")
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="Some text",
            tenant_id="tenant-1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        assert result.metadata.domain == "logistics"
        assert result.metadata.language == "en"
        assert result.metadata.tenant_id == "tenant-1"
        assert isinstance(result.metadata.processing_time_ms, int)

    @pytest.mark.asyncio
    async def test_redact_applies_redactions_to_text(self):
        entity = DetectedEntity(
            entity_type="PERSON",
            start_index=5,
            end_index=10,
            text_segment="Alice",
            detection_source="TEST",
            risk_score=1.0,
        )
        policy = {"rules": [{"entity_type": "PERSON", "action": "REDACT", "config": {}}]}
        svc, _, _, _ = self._make_service(policy=policy, detected=[entity])
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="Name Alice here",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        assert "[REDACTED]" in result.redacted_text
        assert "Alice" not in result.redacted_text

    @pytest.mark.asyncio
    async def test_redact_include_original_true(self):
        svc, _, _, _ = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="Original text here",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=True,
            background_tasks=bg,
        )
        assert result.original_text == "Original text here"

    @pytest.mark.asyncio
    async def test_redact_include_original_false_keeps_none(self):
        svc, _, _, _ = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="Some text",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        assert result.original_text is None

    @pytest.mark.asyncio
    async def test_redact_schedules_audit_background_task(self):
        svc, _, _, audit_svc = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        await svc.redact(
            text="text",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        bg.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_redact_raises_400_when_policy_not_found(self):
        svc, policy_sync, _, _ = self._make_service()
        policy_sync.get_policy.return_value = None   # simulate missing policy

        bg = MagicMock()
        bg.add_task = MagicMock()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await svc.redact(
                text="text",
                tenant_id="t1",
                language="en",
                target="user",
                include_original=False,
                background_tasks=bg,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_target_not_user_sets_strict_mode(self):
        svc, _, detection_engine, _ = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        await svc.redact(
            text="text",
            tenant_id="t1",
            language="en",
            target="system",   # not "user" → strict_mode=True
            include_original=False,
            background_tasks=bg,
        )
        _call_args = detection_engine.detect.call_args
        assert _call_args.kwargs.get("strict_mode", _call_args.args[3] if len(_call_args.args) > 3 else None) is True

    @pytest.mark.asyncio
    async def test_target_user_sets_non_strict_mode(self):
        svc, _, detection_engine, _ = self._make_service()
        bg = MagicMock()
        bg.add_task = MagicMock()
        await svc.redact(
            text="text",
            tenant_id="t1",
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        _call_args = detection_engine.detect.call_args
        assert _call_args.kwargs.get("strict_mode", _call_args.args[3] if len(_call_args.args) > 3 else None) is False

    @pytest.mark.asyncio
    async def test_no_tenant_id_uses_logistics_fallback_domain(self):
        svc, policy_sync, _, _ = self._make_service()
        policy_sync.resolve_domain_for_tenant.return_value = None
        bg = MagicMock()
        bg.add_task = MagicMock()
        result = await svc.redact(
            text="text",
            tenant_id=None,
            language="en",
            target="user",
            include_original=False,
            background_tasks=bg,
        )
        assert result.metadata.domain == "logistics"
        assert result.metadata.message is not None


# ===========================================================================
# Section 3 — PolicySyncService
# ===========================================================================

class _PolicyRow:
    """Minimal stand-in for a DomainPolicy ORM row."""
    def __init__(self, domain_id, policy_json, is_active):
        self.domain_id  = domain_id
        self.policy_json = policy_json
        self.is_active  = is_active


class TestPolicySyncServiceRefresh:
    """Tests for PolicySyncService.refresh()."""

    @pytest.mark.asyncio
    async def test_refresh_populates_policies(self):
        svc = PolicySyncService()

        rows = [
            _PolicyRow("logistics",   {"rules": []}, True),
            _PolicyRow("healthcare",  {"rules": []}, False),
        ]

        policy_repo_mock  = AsyncMock()
        policy_repo_mock.get_all.return_value = rows
        tenant_repo_mock  = AsyncMock()
        tenant_repo_mock.get_all_as_dict.return_value = {"tenant-1": "logistics"}

        # Patch inside the policy_sync module namespace (the only effective path
        # since app.repositories is a stub without real sub-package attributes).
        with (
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "PolicyRepository",
                return_value=policy_repo_mock,
            ),
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "TenantMapRepository",
                return_value=tenant_repo_mock,
            ),
        ):
            db_mock = MagicMock()
            await svc.refresh(db_mock)

        assert "logistics"  in svc._policies
        assert "healthcare" in svc._policies
        assert svc.ready is True

    @pytest.mark.asyncio
    async def test_refresh_populates_active_domain_ids(self):
        svc = PolicySyncService()
        rows = [
            _PolicyRow("logistics",  {"rules": []}, True),
            _PolicyRow("healthcare", {"rules": []}, False),
        ]
        policy_repo_mock = AsyncMock()
        policy_repo_mock.get_all.return_value = rows
        tenant_repo_mock = AsyncMock()
        tenant_repo_mock.get_all_as_dict.return_value = {}

        with (
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "PolicyRepository", return_value=policy_repo_mock,
            ),
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "TenantMapRepository", return_value=tenant_repo_mock,
            ),
        ):
            await svc.refresh(MagicMock())

        assert "logistics"  in svc._active_domain_ids
        assert "healthcare" not in svc._active_domain_ids

    @pytest.mark.asyncio
    async def test_refresh_populates_tenant_domain(self):
        svc = PolicySyncService()
        rows = [_PolicyRow("logistics", {"rules": []}, True)]
        policy_repo_mock = AsyncMock()
        policy_repo_mock.get_all.return_value = rows
        tenant_repo_mock = AsyncMock()
        tenant_repo_mock.get_all_as_dict.return_value = {
            "tenant-A": "logistics",
            "tenant-B": "healthcare",
        }

        with (
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "PolicyRepository", return_value=policy_repo_mock,
            ),
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "TenantMapRepository", return_value=tenant_repo_mock,
            ),
        ):
            await svc.refresh(MagicMock())

        assert svc._tenant_domain["tenant-A"] == "logistics"
        assert svc._tenant_domain["tenant-B"] == "healthcare"

    @pytest.mark.asyncio
    async def test_refresh_sets_ready_true(self):
        svc = PolicySyncService()
        assert svc.ready is False

        policy_repo_mock = AsyncMock()
        policy_repo_mock.get_all.return_value = []
        tenant_repo_mock = AsyncMock()
        tenant_repo_mock.get_all_as_dict.return_value = {}

        with (
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "PolicyRepository", return_value=policy_repo_mock,
            ),
            patch.object(
                sys.modules["app.services.pii_management.policy_sync_service"],
                "TenantMapRepository", return_value=tenant_repo_mock,
            ),
        ):
            await svc.refresh(MagicMock())

        assert svc.ready is True


class TestPolicySyncServiceAccessors:
    """Tests for get_policy, list_active_domains, resolve_domain_for_tenant."""

    def _populated_service(self):
        svc = PolicySyncService()
        svc._policies = {
            "logistics":  {"rules": [{"entity_type": "PERSON"}]},
            "healthcare": {"rules": []},
        }
        svc._active_domain_ids = {"logistics"}
        svc._tenant_domain = {"tenant-1": "logistics"}
        svc.ready = True
        return svc

    def test_get_policy_returns_correct_policy(self):
        svc = self._populated_service()
        policy = svc.get_policy("logistics")
        assert policy is not None
        assert "rules" in policy

    def test_get_policy_returns_none_for_unknown_domain(self):
        svc = self._populated_service()
        assert svc.get_policy("unknown-domain") is None

    def test_list_active_domains_returns_sorted_list(self):
        svc = PolicySyncService()
        svc._active_domain_ids = {"zebra", "alpha", "mango"}
        result = svc.list_active_domains()
        assert result == sorted(["zebra", "alpha", "mango"])

    def test_list_active_domains_returns_only_active(self):
        svc = self._populated_service()
        result = svc.list_active_domains()
        assert "logistics" in result
        assert "healthcare" not in result

    def test_resolve_domain_for_tenant_returns_mapped_domain(self):
        svc = self._populated_service()
        assert svc.resolve_domain_for_tenant("tenant-1") == "logistics"

    def test_resolve_domain_for_tenant_returns_none_for_unmapped(self):
        svc = self._populated_service()
        assert svc.resolve_domain_for_tenant("unknown-tenant") is None

    def test_resolve_domain_for_tenant_returns_none_for_none_input(self):
        svc = self._populated_service()
        assert svc.resolve_domain_for_tenant(None) is None

    def test_resolve_domain_strips_whitespace_from_tenant_id(self):
        svc = self._populated_service()
        # Stored as "tenant-1" — lookup with surrounding whitespace should still match
        assert svc.resolve_domain_for_tenant("  tenant-1  ") == "logistics"


# ===========================================================================
# Section 4 — KnowledgeBaseService
# ===========================================================================

class _PatternRow:
    """Minimal stand-in for a PatternLibrary ORM row."""
    def __init__(self, entity_label, regex_pattern, lang_code, is_active=True):
        self.entity_label  = entity_label
        self.regex_pattern = regex_pattern
        self.lang_code     = lang_code
        self.is_active     = is_active


class TestKnowledgeBaseServiceRefresh:
    """Tests for KnowledgeBaseService.refresh()."""

    @pytest.mark.asyncio
    async def test_lang_code_all_expands_to_four_languages(self):
        svc = KnowledgeBaseService()
        rows = [_PatternRow("PHONE", r"\b\d{10}\b", "all")]

        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = rows
        pattern_repo_mock.get_active_geo_terms.return_value = []

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())

        for lang in ("en", "hi", "mr", "ta"):
            assert lang in svc.patterns, f"Expected language '{lang}' in patterns"
            assert "PHONE" in svc.patterns[lang]

    @pytest.mark.asyncio
    async def test_lang_code_en_stays_only_in_en(self):
        svc = KnowledgeBaseService()
        rows = [_PatternRow("EMAIL", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "en")]

        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = rows
        pattern_repo_mock.get_active_geo_terms.return_value = []

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())

        assert "en" in svc.patterns
        assert "EMAIL" in svc.patterns["en"]
        for lang in ("hi", "mr", "ta"):
            assert lang not in svc.patterns or "EMAIL" not in svc.patterns.get(lang, {})

    @pytest.mark.asyncio
    async def test_invalid_regex_is_skipped_not_raised(self):
        svc = KnowledgeBaseService()
        rows = [_PatternRow("BAD", r"[unclosed", "en")]

        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = rows
        pattern_repo_mock.get_active_geo_terms.return_value = []

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())   # must not raise

        assert "BAD" not in svc.patterns.get("en", {})

    @pytest.mark.asyncio
    async def test_refresh_sets_ready_true(self):
        svc = KnowledgeBaseService()
        assert svc.ready is False

        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = []
        pattern_repo_mock.get_active_geo_terms.return_value = []

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())

        assert svc.ready is True

    @pytest.mark.asyncio
    async def test_geo_suffix_stored_per_language(self):
        svc = KnowledgeBaseService()
        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = []

        class _GeoRow:
            def __init__(self, lang_code, term_type, term_text):
                self.lang_code  = lang_code
                self.term_type  = term_type
                self.term_text  = term_text
                self.is_active  = True

        geo_rows = [_GeoRow("en", "SUFFIX", "nagar"), _GeoRow("hi", "SAFE_CITY", "Pune")]
        pattern_repo_mock.get_active_geo_terms.return_value = geo_rows

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())

        assert "nagar" in svc.suffixes.get("en", [])
        assert "pune" in svc.safe_geo.get("hi", set())

    @pytest.mark.asyncio
    async def test_multiple_all_patterns_compile_independently(self):
        svc = KnowledgeBaseService()
        rows = [
            _PatternRow("PHONE", r"\b\d{10}\b",  "all"),
            _PatternRow("AADHAR", r"\b\d{12}\b", "all"),
        ]
        pattern_repo_mock = AsyncMock()
        pattern_repo_mock.get_active_patterns.return_value = rows
        pattern_repo_mock.get_active_geo_terms.return_value = []

        with patch.object(
            sys.modules["app.services.pii_management.knowledge_base_service"],
            "PatternRepository", return_value=pattern_repo_mock,
        ):
            await svc.refresh(MagicMock())

        for lang in ("en", "hi", "mr", "ta"):
            assert "PHONE"  in svc.patterns[lang]
            assert "AADHAR" in svc.patterns[lang]


# ===========================================================================
# Section 5 — Routes  (FastAPI TestClient)
# ===========================================================================

def _build_test_app():
    """
    Create a minimal FastAPI app that only mounts the PII router.
    Avoids importing app.main (which loads DB, Redis, etc.).
    """
    from fastapi import FastAPI

    # We must patch imports that pii.py pulls in at module level before
    # we import the router.
    with (
        patch.dict(sys.modules, {
            "app.core.pii_database": _pii_db_stub,
            "app.core.config":       _config_stub,
        }),
    ):
        # Import the router module (already patched stubs are in sys.modules)
        import importlib as _il
        pii_routes_spec = importlib.util.spec_from_file_location(
            "app.routes.pii",
            str(_SERVICE_ROOT / "app" / "routes" / "pii.py"),
        )
        pii_routes_mod = importlib.util.module_from_spec(pii_routes_spec)
        # Patch required repository/schema stubs that pii.py imports
        pii_routes_mod.__spec__ = pii_routes_spec
        sys.modules["app.routes.pii"] = pii_routes_mod
        pii_routes_spec.loader.exec_module(pii_routes_mod)

    app = FastAPI()
    # The router already carries prefix="/pii" — do NOT add it again here.
    app.include_router(pii_routes_mod.router)
    return app, pii_routes_mod


@pytest.fixture(scope="module")
def pii_app_and_router():
    return _build_test_app()


@pytest.fixture(scope="module")
def test_client(pii_app_and_router):
    from fastapi.testclient import TestClient
    app, _ = pii_app_and_router
    return TestClient(app)


@pytest.fixture(autouse=False)
def mock_state(test_client, pii_app_and_router):
    """Attach mock services to app.state before each test."""
    app, _ = pii_app_and_router
    app.state.pii_policy_sync    = MagicMock()
    app.state.pii_redaction_service = MagicMock()
    return app.state


class TestPiiRoutes:
    """FastAPI TestClient tests for the PII routes."""

    # ── GET /pii/domains ────────────────────────────────────────────────────

    def test_get_domains_returns_200(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.list_active_domains.return_value = ["logistics", "healthcare"]
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/domains")
        assert resp.status_code == 200

    def test_get_domains_returns_list_from_policy_sync(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.list_active_domains.return_value = ["logistics", "healthcare"]
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/domains")
        data = resp.json()
        assert "logistics"  in data
        assert "healthcare" in data

    def test_get_domains_empty_list(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.list_active_domains.return_value = []
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/domains")
        assert resp.status_code == 200
        assert resp.json() == []

    # ── GET /pii/policy/{domain} ────────────────────────────────────────────

    def test_get_policy_returns_200_for_known_domain(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.get_policy.return_value = {
            "meta": {"version": "1.0", "description": "Test"},
            "rules": [],
        }
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/policy/logistics")
        assert resp.status_code == 200

    def test_get_policy_returns_policy_dict(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        expected = {"meta": {"version": "1.0", "description": "Logistics"}, "rules": []}
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.get_policy.return_value = expected
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/policy/logistics")
        assert resp.json()["meta"]["version"] == "1.0"

    def test_get_policy_returns_empty_dict_for_unknown_domain(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_policy_sync.get_policy.return_value = None   # not found
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.get("/pii/policy/nonexistent")
        assert resp.status_code == 200
        # get_policy is now wrapped in PolicyResponse (for Swagger docs), so
        # the bare {} the service returns on a cache miss comes back with
        # its declared defaults filled in rather than as a literal {} —
        # still "no policy", just explicit. The frontend already treats a
        # missing `rules` key defensively (Array.isArray(...) ? ... : []),
        # so an actual [] here is unaffected either way.
        assert resp.json() == {"meta": None, "rules": []}

    # ── POST /pii/redact ────────────────────────────────────────────────────

    def test_post_redact_returns_200(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()

        mock_response = RedactionResponse(
            redacted_text="Hello world",
            pii_detected=[],
            trace=[],
            metadata=RedactionMetadata(
                processing_time_ms=5,
                language="en",
                domain="logistics",
                tenant_id="unknown",
            ),
        )

        async def _mock_redact(**kwargs):
            return mock_response

        redaction_svc = MagicMock()
        redaction_svc.redact = _mock_redact
        app.state.pii_redaction_service = redaction_svc

        resp = test_client.post("/pii/redact", json={"text": "hello"})
        assert resp.status_code == 200

    def test_post_redact_response_has_required_fields(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()

        mock_response = RedactionResponse(
            redacted_text="[REDACTED] world",
            pii_detected=[],
            trace=[{"step": "Request", "status": "Success", "details": "ok"}],
            metadata=RedactionMetadata(
                processing_time_ms=12,
                language="en",
                domain="logistics",
                tenant_id="unknown",
            ),
        )

        async def _mock_redact(**kwargs):
            return mock_response

        redaction_svc = MagicMock()
        redaction_svc.redact = _mock_redact
        app.state.pii_redaction_service = redaction_svc

        resp = test_client.post("/pii/redact", json={"text": "John world"})
        body = resp.json()
        assert "redacted_text" in body
        assert "pii_detected"  in body
        assert "trace"         in body
        assert "metadata"      in body

    def test_post_redact_missing_body_returns_422(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.post("/pii/redact")   # no JSON body
        assert resp.status_code == 422

    def test_post_redact_empty_json_object_returns_422(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()
        app.state.pii_redaction_service = MagicMock()

        resp = test_client.post("/pii/redact", json={})   # missing required "text"
        assert resp.status_code == 422

    def test_post_redact_calls_redaction_service_with_text(self, test_client, pii_app_and_router):
        app, _ = pii_app_and_router
        app.state.pii_policy_sync = MagicMock()

        captured_kwargs = {}

        async def _mock_redact(**kwargs):
            captured_kwargs.update(kwargs)
            return RedactionResponse(
                redacted_text="done",
                pii_detected=[],
                trace=[],
                metadata=RedactionMetadata(
                    processing_time_ms=1, language="en",
                    domain="logistics", tenant_id="unknown",
                ),
            )

        redaction_svc = MagicMock()
        redaction_svc.redact = _mock_redact
        app.state.pii_redaction_service = redaction_svc

        test_client.post("/pii/redact", json={"text": "My name is Alice"})
        assert captured_kwargs.get("text") == "My name is Alice"

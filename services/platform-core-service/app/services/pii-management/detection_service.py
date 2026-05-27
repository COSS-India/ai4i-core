"""
DetectionEngine — three-layer PII entity detection.

Layers (in order):
  1. AI extraction  — calls the external NER service for contextual entity recognition.
  2. Regex scan     — applies compiled patterns from KnowledgeBaseService.
  3. Quasi-identifiers — keyword matching for occupations and gender terms.

All layers run for every request; results are deduplicated by position at the
redaction stage (redaction_service.py).
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.pii_management.redaction import DetectedEntity
from .knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

# ── Static lookup tables ──────────────────────────────────────────────────

_FALSE_POSITIVES: frozenset = frozenset({
    "phone", "mobile", "email", "address", "number",
    "फ़ोन", "मोबाइल", "ईमेल", "पता", "नंबर",
})

_COMMON_OCCUPATIONS: frozenset = frozenset({
    "farmer", "driver", "teacher", "engineer", "doctor", "nurse", "worker",
})

_GENDER_TERMS: frozenset = frozenset({
    "male", "female", "man", "woman", "boy", "girl", "transgender",
})

# NER labels → canonical entity type
_AI_LABEL_MAP: Dict[str, str] = {
    "GPE": "LOCATION", "LOC": "LOCATION", "FAC": "LOCATION", "ORG": "LOCATION",
    "PERSON": "PERSON",
}


class DetectionEngine:
    """Stateless detection engine. Depends on KnowledgeBaseService for patterns."""

    def __init__(self, kb: KnowledgeBaseService, ner_service_url: str) -> None:
        self._kb = kb
        self._ner_url = ner_service_url

    # ── Layer 1: AI (NER service) ─────────────────────────────────────────

    async def _fetch_ai_entities(self, text: str, lang: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    self._ner_url,
                    json={"text": text, "lang": lang},
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return resp.json().get("entities", [])
            except Exception as exc:
                logger.warning("NER service call failed: %s", exc)
        return []

    # ── Layer 3: Quasi-identifiers ────────────────────────────────────────

    def _detect_quasi_identifiers(self, text: str) -> List[DetectedEntity]:
        found: List[DetectedEntity] = []
        words = re.findall(r"\b\w+\b", text.lower())
        for word in words:
            if word in _COMMON_OCCUPATIONS:
                for m in re.finditer(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
                    found.append(DetectedEntity(
                        entity_type="OCCUPATION",
                        start_index=m.start(), end_index=m.end(),
                        text_segment=m.group(),
                        detection_source="KEYWORD",
                        risk_score=0.3,
                    ))
            if word in _GENDER_TERMS:
                for m in re.finditer(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
                    found.append(DetectedEntity(
                        entity_type="GENDER",
                        start_index=m.start(), end_index=m.end(),
                        text_segment=m.group(),
                        detection_source="KEYWORD",
                        risk_score=0.2,
                    ))
        return found

    # ── Main detection entry point ────────────────────────────────────────

    async def detect(
        self,
        text: str,
        rules: List[Dict[str, Any]],
        trace_log: List[Dict[str, Any]],
        strict_mode: bool = False,
        lang: str = "en",
    ) -> List[DetectedEntity]:
        """
        Run all three detection layers and return a flat list of DetectedEntity objects.

        Parameters
        ----------
        text        : input text to scan
        rules       : policy rules for the resolved domain
        trace_log   : list to append step summaries to (mutated in-place)
        strict_mode : True when X-Target != "user" (raises AI confidence scores)
        lang        : language code from X-Language header
        """
        detected: List[DetectedEntity] = []
        patterns = self._kb.patterns.get(lang, {})
        active_types = {r["entity_type"] for r in rules}

        # ── Layer 1: AI extraction ────────────────────────────────────────
        ai_entities = await self._fetch_ai_entities(text, lang)
        ai_count = 0
        for ent in ai_entities:
            ent_text = ent.get("text", "")
            ent_label = ent.get("label", "")
            if ent_text.lower() in _FALSE_POSITIVES:
                continue
            mapped = _AI_LABEL_MAP.get(ent_label, ent_label)
            if mapped not in active_types:
                continue
            detected.append(DetectedEntity(
                entity_type=mapped,
                start_index=ent["start_char"],
                end_index=ent["end_char"],
                text_segment=ent_text,
                detection_source=f"AI: {ent_label}",
                risk_score=1.0 if strict_mode else 0.9,
            ))
            ai_count += 1
        trace_log.append({
            "step": "AI Extraction",
            "status": "Success",
            "details": f"AI identified {ai_count} entities.",
        })

        # ── Layer 2: Regex scan ───────────────────────────────────────────
        regex_count = 0
        for rule in rules:
            entity_type = rule["entity_type"]
            custom_rx = rule.get("custom_regex")

            if custom_rx:
                # Domain-specific custom regex (e.g. TRACKING_ID, VEHICLE_REG)
                try:
                    for m in re.finditer(custom_rx, text, re.UNICODE | re.IGNORECASE):
                        val, st, en = (
                            (m.group(1), m.start(1), m.end(1))
                            if m.lastindex
                            else (m.group(), m.start(), m.end())
                        )
                        detected.append(DetectedEntity(
                            entity_type=entity_type,
                            start_index=st, end_index=en,
                            text_segment=val,
                            detection_source="REGEX: Custom",
                            risk_score=1.0,
                        ))
                        regex_count += 1
                except re.error as exc:
                    logger.warning("Invalid custom_regex for %s: %s", entity_type, exc)

            elif entity_type in patterns:
                # Pattern library regex
                for m in patterns[entity_type].finditer(text):
                    val, st, en = (
                        (m.group(1), m.start(1), m.end(1))
                        if m.lastindex
                        else (m.group(), m.start(), m.end())
                    )
                    if val.lower() in _FALSE_POSITIVES:
                        continue
                    detected.append(DetectedEntity(
                        entity_type=entity_type,
                        start_index=st, end_index=en,
                        text_segment=val,
                        detection_source=f"REGEX: {entity_type}",
                        risk_score=1.0,
                    ))
                    regex_count += 1

        trace_log.append({
            "step": "Regex Layer",
            "status": "Success",
            "details": f"Matched {regex_count} patterns.",
        })

        # ── Layer 3: Quasi-identifiers ────────────────────────────────────
        detected.extend(self._detect_quasi_identifiers(text))
        trace_log.append({
            "step": "Risk Assessment",
            "status": "Success",
            "details": f"Final Entity Count: {len(detected)}",
        })

        return detected

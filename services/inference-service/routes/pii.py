"""Presidio analyze/anonymize test endpoints and the policy simulation."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/pii", tags=["PII Test"])


class PiiRequest(BaseModel):
    text: str
    language: str = "en"


class EntityResult(BaseModel):
    entityType: str
    start: int
    end: int
    score: float


class AnalyzeResponse(BaseModel):
    entities: List[EntityResult]


class AnonymizeRequest(PiiRequest):
    # The /analyze output for this text, as is. Omit it to analyze here.
    analyzerResults: Optional[List[EntityResult]] = None


class AnonymizedItem(BaseModel):
    entityType: str
    start: int
    end: int
    text: str
    operator: str


class AnonymizeResponse(BaseModel):
    anonymizedText: str
    entities: List[EntityResult]
    items: List[AnonymizedItem]
    # {entity_type: {original value: token}}; holds raw PII.
    entityMapping: Dict[str, Dict[str, str]]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: PiiRequest):
    from services.pii.engine import get_engine
    engine = get_engine()
    results = engine.analyze(req.text, req.language)
    return AnalyzeResponse(
        entities=[
            EntityResult(entityType=r.entity_type, start=r.start, end=r.end, score=round(r.score, 4))
            for r in results
        ]
    )


@router.post("/anonymize", response_model=AnonymizeResponse)
def anonymize(req: AnonymizeRequest):
    from presidio_analyzer import RecognizerResult

    from services.pii.engine import get_engine
    engine = get_engine()
    if req.analyzerResults is None:
        results = engine.analyze(req.text, req.language)
    else:
        results = [
            RecognizerResult(e.entityType, e.start, e.end, e.score) for e in req.analyzerResults
        ]
    anonymized, entity_mapping = engine.anonymize(req.text, results)
    return AnonymizeResponse(
        anonymizedText=anonymized.text,
        entities=[
            EntityResult(entityType=r.entity_type, start=r.start, end=r.end, score=round(r.score, 4))
            for r in results
        ],
        items=[
            AnonymizedItem(
                entityType=i.entity_type, start=i.start, end=i.end, text=i.text, operator=i.operator
            )
            for i in anonymized.items
        ],
        entityMapping=entity_mapping,
    )


class SimulatePolicyType(BaseModel):
    """A policy_type row as platform-core returns it (GET /policies/policy-types)."""

    id: Optional[int] = None
    policy_type: str
    policy_fields: Dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    text: str
    policyTypes: List[SimulatePolicyType]


class Replacement(BaseModel):
    original: str
    output: str


class DetectedPii(BaseModel):
    entityType: str
    policyType: str
    instances: int
    replacements: List[Replacement]


class SimulateResponse(BaseModel):
    originalText: str
    sanitizedText: str
    detected: List[DetectedPii]


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    """Detect the policy's PII types in text and replace them with tokens."""
    from services.pii.simulation import InvalidPolicyError, PolicyType, simulate as run

    try:
        result = run(
            req.text,
            [PolicyType(pt.policy_type, pt.policy_fields) for pt in req.policyTypes],
        )
    except InvalidPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SimulateResponse(
        originalText=req.text,
        sanitizedText=result.sanitized_text,
        detected=[
            DetectedPii(
                entityType=d.entity_type,
                policyType=d.policy_type,
                instances=d.instances,
                replacements=[Replacement(original=o, output=t) for o, t in d.replacements.items()],
            )
            for d in result.detected
        ],
    )

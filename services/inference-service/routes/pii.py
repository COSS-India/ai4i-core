"""Presidio analyze/anonymize test endpoints and the policy simulation."""

from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

router = APIRouter(prefix="/pii", tags=["PII Test"])

# Matches platform-core's NAME_MAX_LEN for policy type names.
NAME_MAX_LEN = 100
# spaCy refuses text over 1,000,000 characters (a 500); stay well below it.
MAX_SIMULATE_TEXT_LEN = 100_000
MAX_POLICY_TYPES = 50
MAX_CUSTOM_FIELDS = 100
MAX_REGEX_LEN = 1000

EntityName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LEN)
]


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


class AnalyzerResultIn(BaseModel):
    entityType: EntityName
    # strict: lax mode would accept true as 1 and "5" as 5.
    start: int = Field(..., ge=0, strict=True)
    end: int = Field(..., ge=0, strict=True)
    score: float = Field(..., ge=0, le=1)


class AnonymizeRequest(PiiRequest):
    # The /analyze output for this text, as is. Omit it to analyze here.
    analyzerResults: Optional[List[AnalyzerResultIn]] = None

    @model_validator(mode="after")
    def spans_inside_text(self):
        # Presidio raises (a 500) for a span past the end of the text, and
        # silently duplicates text for start > end.
        for e in self.analyzerResults or []:
            if not e.start < e.end <= len(self.text):
                raise ValueError(
                    f"analyzerResults span {e.start}-{e.end} is not inside the text "
                    f"(length {len(self.text)}); start must be less than end."
                )
        return self


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


# platform-core's policy_fields JSONB. extra="allow": keys this endpoint does
# not use (examples, handling, implementation_method, ...) are accepted.
class CustomFieldIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity_name: EntityName
    # Not stripped: spaces can be part of the pattern. pattern=\S rejects blank.
    regex: Annotated[str, StringConstraints(max_length=MAX_REGEX_LEN, pattern=r"\S")]


class ModelEntityIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity_name: EntityName


class PolicyFieldsIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    custom_field: List[CustomFieldIn] = Field(default_factory=list, max_length=MAX_CUSTOM_FIELDS)
    # [{"en": [{"entity_name": "PERSON"}], "hi": [...]}]
    model_supported_field: List[Dict[str, List[ModelEntityIn]]] = Field(default_factory=list)


class SimulatePolicyType(BaseModel):
    """A policy_type row as platform-core returns it (GET /policies/policy-types)."""

    id: Optional[int] = None
    policy_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LEN)
    ]
    policy_fields: PolicyFieldsIn = Field(default_factory=PolicyFieldsIn)


class SimulateRequest(BaseModel):
    text: str = Field(..., max_length=MAX_SIMULATE_TEXT_LEN)
    policyTypes: List[SimulatePolicyType] = Field(..., max_length=MAX_POLICY_TYPES)


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


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    responses={400: {"description": "Malformed request or policy fields, an invalid regex, or a regex that timed out."}},
)
def simulate(req: SimulateRequest):
    """Detect the policy's PII types in text and replace them with numbered tokens.

    The text's language is detected automatically.
    """
    from services.pii.simulation import CustomField, InvalidPolicyError, PolicyType, simulate as run

    policy_types = []
    for pt in req.policyTypes:
        model_entities: Dict[str, List[str]] = {}
        for by_language in pt.policy_fields.model_supported_field:
            for lang, entries in by_language.items():
                model_entities.setdefault(lang, []).extend(e.entity_name for e in entries)
        policy_types.append(
            PolicyType(
                name=pt.policy_type,
                custom_fields=[
                    CustomField(cf.entity_name, cf.regex) for cf in pt.policy_fields.custom_field
                ],
                model_entities=model_entities,
            )
        )

    try:
        result = run(req.text, policy_types)
    except InvalidPolicyError as exc:
        # 400 like the app's request-validation handler (app_factory.py).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

"""Presidio analyze/anonymize test endpoints and the policy simulation."""

import logging
import re
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from services.guardrail import (
    GuardrailError,
    PolicyFieldsError,
    PolicyNotFoundError,
    get_policy,
    parse_policy_types,
)
from services.pii.engine import get_engine
from services.pii.model_registry import get_spacy_lang_code
from config import settings
from services.pii.simulation import InvalidPolicyError, simulate as run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pii", tags=["PII Test"])

# Matches platform-core's NAME_MAX_LEN for policy type names.
NAME_MAX_LEN = 100
# spaCy refuses text over 1,000,000 characters (a 500); stay well below it.
MAX_SIMULATE_TEXT_LEN = 100_000
# platform-core's ROLE_ADMIN; reading a policy there is Adopter Admin only.
ROLE_ADMIN = 1

# strip_whitespace leaves zero-width characters, so "\u200b" would pass
# min_length and show up as a token like <_1>; require a visible character.
EntityName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=NAME_MAX_LEN,
        pattern=r"[^\s\u200b-\u200d\u2060\ufeff]",
    ),
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


_SUPPORTED_ENTITIES_EN_EXAMPLE = {
    "language": "en",
    "model": "en_core_web_lg",
    "entities": [
        "CREDIT_CARD", "CRYPTO", "DATE_TIME", "EMAIL_ADDRESS", "IBAN_CODE",
        "IP_ADDRESS", "LOCATION", "MEDICAL_LICENSE", "NRP", "ORGANIZATION",
        "PERSON", "PHONE_NUMBER", "URL", "US_BANK_NUMBER", "US_DRIVER_LICENSE",
        "US_ITIN", "US_PASSPORT", "US_SSN",
    ],
}

_SUPPORTED_ENTITIES_HI_EXAMPLE = {
    "language": "hi",
    "model": "xx_ent_wiki_sm",
    "entities": [
        "CREDIT_CARD", "CRYPTO", "DATE_TIME", "EMAIL_ADDRESS", "IBAN_CODE",
        "IP_ADDRESS", "MEDICAL_LICENSE", "NRP", "PHONE_NUMBER", "URL",
        "US_BANK_NUMBER", "US_DRIVER_LICENSE", "US_ITIN", "US_PASSPORT", "US_SSN",
    ],
}

_SUPPORTED_ENTITIES_DE_EXAMPLE = {
    "language": "de",
    "model": "xx_ent_wiki_sm",
    "entities": [
        "CREDIT_CARD", "CRYPTO", "DATE_TIME", "EMAIL_ADDRESS", "IBAN_CODE",
        "IP_ADDRESS", "LOCATION", "MEDICAL_LICENSE", "NRP", "ORGANIZATION",
        "PERSON", "PHONE_NUMBER", "URL", "US_BANK_NUMBER", "US_DRIVER_LICENSE",
        "US_ITIN", "US_PASSPORT", "US_SSN",
    ],
}


class SupportedEntitiesResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                _SUPPORTED_ENTITIES_EN_EXAMPLE,
                _SUPPORTED_ENTITIES_HI_EXAMPLE,
                _SUPPORTED_ENTITIES_DE_EXAMPLE,
            ]
        }
    )

    language: str
    model: str
    entities: List[str]


@router.get("/entities", response_model=SupportedEntitiesResponse)
def supported_entities(language: str = "en", country: Optional[str] = None):
    """Return entity types detectable by Presidio for the given language.

    English uses the en_core_web_lg spaCy model; all other languages use
    xx_ent_wiki_sm.  Languages without NER coverage in xx_ent_wiki_sm (e.g.
    hi, zh) will only include pattern-based entities such as EMAIL_ADDRESS.

    Pass country (e.g. "IN", "US") to restrict results to universal entities
    plus those specific to that country.  Omit it to get all entities.
    """
    engine = get_engine()
    lang_code = get_spacy_lang_code(language)
    model_name = (
        settings.PII_SPACY_EN_MODEL if lang_code == "en" else settings.PII_SPACY_MULTILINGUAL_MODEL
    )
    entities = sorted(engine.detectable_entities(language, country))
    return SupportedEntitiesResponse(language=language, model=model_name, entities=entities)


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


class SimulateRequest(BaseModel):
    text: str = Field(..., max_length=MAX_SIMULATE_TEXT_LEN)
    # platform-core policy id; its policy types are loaded the same way the
    # inference guardrail loads them (Redis, then platform-core).
    policyId: int = Field(..., gt=0, le=2_147_483_647, strict=True)


class Replacement(BaseModel):
    original: str
    output: str


class DetectedPii(BaseModel):
    entityType: str
    # Every policy type that defines this entity (two types can define the
    # same entity_name with different regexes; both run).
    policyTypes: List[str]
    instances: int
    replacements: List[Replacement]


class SimulateResponse(BaseModel):
    originalText: str
    sanitizedText: str
    detected: List[DetectedPii]


def require_admin(x_permission_ids: str = Header(default="")) -> None:
    """Same rule as platform-core's GET /policies/{id}: Adopter Admin only.
    X-Permission-IDs is injected by the gateway after token validation."""
    # Compare as text: int() of a huge digit run raises (a 500).
    if str(ROLE_ADMIN) not in {m.lstrip("0") for m in re.findall(r"\d+", x_permission_ids)}:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    dependencies=[Depends(require_admin)],
    responses={
        400: {"description": "Malformed request; policy fields that cannot be used, an invalid regex, or regexes that ran out of time."},
        403: {"description": "The caller is not an Adopter Admin."},
        404: {"description": "No policy with this id."},
        503: {"description": "The policy could not be loaded from Redis or platform-core."},
    },
)
async def simulate(req: SimulateRequest):
    """Detect the policy's PII types in text and replace them with numbered tokens.

    The policy is loaded and parsed exactly as the inference guardrail does,
    so the result matches what inference masks. It runs whether or not the
    policy is active, so a draft can be tried before it is switched on;
    inference applies only active policies that are global or attached to
    the calling app.

    The text's language is detected automatically.
    """
    try:
        policy = await get_policy(req.policyId)
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuardrailError as exc:
        # The message names internal config and upstream status codes; log it
        # rather than returning it to the caller.
        logger.warning("Simulate could not load policy_id=%s: %s", req.policyId, exc)
        raise HTTPException(
            status_code=503, detail="The policy could not be loaded; try again later."
        ) from exc

    try:
        policy_types = parse_policy_types(policy)
        # spaCy and the policy regexes are CPU-bound; keep them off the event loop.
        result = await run_in_threadpool(run, req.text, policy_types)
    except (PolicyFieldsError, InvalidPolicyError) as exc:
        # 400 like the app's request-validation handler (app_factory.py).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SimulateResponse(
        originalText=req.text,
        sanitizedText=result.sanitized_text,
        detected=[
            DetectedPii(
                entityType=d.entity_type,
                policyTypes=d.policy_types,
                instances=d.instances,
                replacements=[Replacement(original=o, output=t) for o, t in d.replacements.items()],
            )
            for d in result.detected
        ],
    )

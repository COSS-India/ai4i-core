"""Presidio analyze/anonymize test endpoints and the policy simulation."""

from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from services.pii.engine import get_engine
from services.pii.model_registry import get_spacy_lang_code
from config import settings
from services.pii.simulation import CustomField, InvalidPolicyError, PolicyType, simulate as run

router = APIRouter(prefix="/pii", tags=["PII Test"])

# Matches platform-core's NAME_MAX_LEN for policy type names.
NAME_MAX_LEN = 100
# spaCy refuses text over 1,000,000 characters (a 500); stay well below it.
MAX_SIMULATE_TEXT_LEN = 100_000
MAX_POLICY_TYPES = 50
MAX_DOMAINS = 20
# Totals across the whole request (all policy types and domains). Presidio's
# recognizer selection grows with entities x recognizers, so per-list caps
# that multiply out to 100,000 fields are not enough.
MAX_CUSTOM_FIELDS = 100
MAX_MODEL_ENTITIES = 100
MAX_REGEX_LEN = 1000

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
def supported_entities(language: str = "en"):
    """Return entity types detectable by Presidio for the given language.

    English uses the en_core_web_lg spaCy model; all other languages use
    xx_ent_wiki_sm.  Languages without NER coverage in xx_ent_wiki_sm (e.g.
    hi, zh) will only include pattern-based entities such as EMAIL_ADDRESS.
    """


    engine = get_engine()
    lang_code = get_spacy_lang_code(language)
    model_name = (
        settings.PII_SPACY_EN_MODEL if lang_code == "en" else settings.PII_SPACY_MULTILINGUAL_MODEL
    )
    entities = sorted(engine.detectable_entities(language))
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


# platform-core's policy_fields JSONB, keyed by domain (#1738):
#   {"Finance": {"custom_field": [...], "model_supported_field": [...]}}
# Every domain section sent is applied; the caller sends only the policy
# types (and domains) it wants simulated.
# Entries allow extra keys (examples, mode, ...); a domain's own keys do not,
# so a shape mismatch is a 400 rather than a silently empty result.
class CustomFieldIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity_name: EntityName
    # Not stripped: spaces can be part of the pattern. pattern=\S rejects blank.
    regex: Annotated[str, StringConstraints(max_length=MAX_REGEX_LEN, pattern=r"\S")]


class ModelEntityIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity_name: EntityName


class DomainFieldsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    custom_field: List[CustomFieldIn] = Field(default_factory=list, max_length=MAX_CUSTOM_FIELDS)
    # [{"en": [{"entity_name": "PERSON"}], "hi": [...]}]
    model_supported_field: List[
        Dict[str, Annotated[List[ModelEntityIn], Field(max_length=MAX_MODEL_ENTITIES)]]
    ] = Field(default_factory=list, max_length=MAX_MODEL_ENTITIES)


class SimulatePolicyType(BaseModel):
    """A policy_type row as platform-core returns it (GET /policies/policy-types)."""

    id: Optional[int] = None
    policy_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LEN)
    ]
    policy_fields: Dict[EntityName, DomainFieldsIn] = Field(
        default_factory=dict, max_length=MAX_DOMAINS
    )


class SimulateRequest(BaseModel):
    text: str = Field(..., max_length=MAX_SIMULATE_TEXT_LEN)
    policyTypes: List[SimulatePolicyType] = Field(..., max_length=MAX_POLICY_TYPES)

    @model_validator(mode="after")
    def cap_fields_per_request(self):
        domains = [d for pt in self.policyTypes for d in pt.policy_fields.values()]
        custom = sum(len(d.custom_field) for d in domains)
        model = sum(
            len(entries)
            for d in domains
            for by_language in d.model_supported_field
            for entries in by_language.values()
        )
        if custom > MAX_CUSTOM_FIELDS:
            raise ValueError(
                f"{custom} custom_field entries in total; at most {MAX_CUSTOM_FIELDS} per request."
            )
        if model > MAX_MODEL_ENTITIES:
            raise ValueError(
                f"{model} model_supported_field entities in total; "
                f"at most {MAX_MODEL_ENTITIES} per request."
            )
        return self


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


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    responses={400: {"description": "Malformed request or policy fields, an invalid regex, or regexes that ran out of time."}},
)
def simulate(req: SimulateRequest):
    """Detect the policy's PII types in text and replace them with numbered tokens.

    The text's language is detected automatically.
    """


    policy_types = []
    for pt in req.policyTypes:
        custom_fields: List[CustomField] = []
        seen: set = set()
        model_entities: Dict[str, List[str]] = {}
        for fields in pt.policy_fields.values():
            for cf in fields.custom_field:
                # The same entity and regex in several domains runs once.
                if (cf.entity_name, cf.regex) not in seen:
                    seen.add((cf.entity_name, cf.regex))
                    custom_fields.append(CustomField(cf.entity_name, cf.regex))
            for by_language in fields.model_supported_field:
                for lang, entries in by_language.items():
                    model_entities.setdefault(lang, []).extend(e.entity_name for e in entries)
        policy_types.append(
            PolicyType(
                name=pt.policy_type,
                custom_fields=custom_fields,
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
                policyTypes=d.policy_types,
                instances=d.instances,
                replacements=[Replacement(original=o, output=t) for o, t in d.replacements.items()],
            )
            for d in result.detected
        ],
    )

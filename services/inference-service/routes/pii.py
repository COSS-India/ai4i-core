"""Temporary test endpoints for Presidio analyze and anonymize."""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

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


class AnonymizeResponse(BaseModel):
    anonymizedText: str
    entities: List[EntityResult]


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
def anonymize(req: PiiRequest):
    from services.pii.engine import get_engine
    engine = get_engine()
    results = engine.analyze(req.text, req.language)
    anonymized = engine.anonymize(req.text, results)
    return AnonymizeResponse(
        anonymizedText=anonymized,
        entities=[
            EntityResult(entityType=r.entity_type, start=r.start, end=r.end, score=round(r.score, 4))
            for r in results
        ]
    )

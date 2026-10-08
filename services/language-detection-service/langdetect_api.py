"""Language detection using the langdetect library (character n-gram model)."""

import os

import langdetect
from fastapi import FastAPI, HTTPException
from langdetect.detector_factory import DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from pydantic import BaseModel

app = FastAPI(title="Language Detection Service (langdetect)")

# English + the Indian languages langdetect ships profiles for.
# langdetect has no profiles for Odia, Assamese, Santali or Manipuri.
SUPPORTED_LANGS = ["en", "hi", "mr", "ne", "bn", "pa", "gu", "ta", "te", "kn", "ml", "ur"]


def _build_factory() -> DetectorFactory:
    """Load only the supported language profiles so results stay within them."""
    profiles_dir = os.path.join(os.path.dirname(langdetect.__file__), "profiles")
    profiles = []
    for lang in SUPPORTED_LANGS:
        with open(os.path.join(profiles_dir, lang), encoding="utf-8") as f:
            profiles.append(f.read())
    factory = DetectorFactory()
    factory.load_json_profile(profiles)
    # langdetect is randomised; a fixed seed makes results repeatable.
    factory.set_seed(0)
    return factory


FACTORY = _build_factory()


class DetectRequest(BaseModel):
    text: str


class Candidate(BaseModel):
    language: str
    probability: float


class DetectResponse(BaseModel):
    language: str
    confidence: float
    candidates: list[Candidate]


def detect(text: str) -> DetectResponse:
    detector = FACTORY.create()
    detector.append(text)
    try:
        results = detector.get_probabilities()
    except LangDetectException as e:
        raise HTTPException(status_code=422, detail=str(e))
    candidates = [Candidate(language=r.lang, probability=round(r.prob, 4)) for r in results]
    return DetectResponse(
        language=candidates[0].language,
        confidence=candidates[0].probability,
        candidates=candidates,
    )


@app.post("/detect", response_model=DetectResponse)
def detect_language(req: DetectRequest) -> DetectResponse:
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    return detect(req.text)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8091)

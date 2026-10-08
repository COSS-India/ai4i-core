"""Lightweight language detection based on Unicode script ranges."""

import unicodedata
from collections import Counter

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Language Detection Service")

# Unicode script name prefix (from unicodedata.name) -> language code.
# Only English and Indian languages are supported. Scripts shared by several
# languages map to the most common one (e.g. Devanagari -> hi, Bengali -> bn).
SCRIPT_TO_LANG = {
    "LATIN": "en",
    "DEVANAGARI": "hi",
    "BENGALI": "bn",
    "GURMUKHI": "pa",
    "GUJARATI": "gu",
    "ORIYA": "or",
    "TAMIL": "ta",
    "TELUGU": "te",
    "KANNADA": "kn",
    "MALAYALAM": "ml",
    "ARABIC": "ur",
    "OL CHIKI": "sat",
    "MEETEI MAYEK": "mni",
}


class DetectRequest(BaseModel):
    text: str


class DetectResponse(BaseModel):
    language: str
    script: str
    confidence: float


def char_script(ch: str) -> str | None:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for script in SCRIPT_TO_LANG:
        if name.startswith(script):
            return script
    return None


def detect(text: str) -> DetectResponse:
    counts = Counter(s for ch in text if ch.isalpha() and (s := char_script(ch)))
    if not counts:
        raise HTTPException(status_code=422, detail="No detectable script in text")
    script, hits = counts.most_common(1)[0]
    return DetectResponse(
        language=SCRIPT_TO_LANG[script],
        script=script,
        confidence=round(hits / sum(counts.values()), 2),
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

    uvicorn.run(app, host="0.0.0.0", port=8090)

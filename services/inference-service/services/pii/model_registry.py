"""Maps request language codes to spaCy model names loaded from config."""

from config import settings

# English gets the large English model; every other language falls back to
# the multilingual model. Both are loaded once at engine init time.
LANGUAGE_MODEL_MAP: dict[str, str] = {
    "en": settings.PII_SPACY_EN_MODEL,
}
MULTILINGUAL_MODEL: str = settings.PII_SPACY_MULTILINGUAL_MODEL


def get_spacy_lang_code(source_language: str) -> str:
    """Return the spaCy lang code to pass to Presidio's AnalyzerEngine.

    Presidio resolves the NLP pipeline by lang code, not by model name.
    The multilingual model is registered under "xx".
    """
    return "en" if source_language == "en" else "xx"

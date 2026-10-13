"""Detect the language of input text with langdetect."""

import logging
from typing import Iterable, Optional

from langdetect import DetectorFactory, LangDetectException, detect_langs
from langdetect.detector_factory import init_factory

logger = logging.getLogger(__name__)

# langdetect is non-deterministic unless seeded: the same text could get a
# different language (and so a different spaCy model) on each request.
DetectorFactory.seed = 0

# langdetect loads its profiles lazily and publishes the factory before they
# finish loading, so two concurrent first calls can detect against a
# half-loaded factory. Load them once here; the import lock serialises it.
init_factory()

DEFAULT_LANGUAGE = "en"


def detect_language(text: str, candidates: Optional[Iterable[str]] = None) -> str:
    """Return the ISO 639-1 code of text, e.g. "en", "hi".

    With candidates, return the most probable language among them. langdetect
    misreads short text ("Email arjun@college.edu" -> "et"), but the right
    language usually still ranks among its guesses.

    Falls back to "en" when there is nothing to detect from (empty text, or
    only digits and symbols) or when no candidate is among the guesses.
    """
    try:
        # langdetect returns region variants for some languages ("zh-cn").
        ranked = [guess.lang.split("-")[0] for guess in detect_langs(text)]
    except LangDetectException:
        logger.debug("Language detection failed; using %s", DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE
    if candidates is not None:
        allowed = set(candidates)
        ranked = [lang for lang in ranked if lang in allowed]
    return ranked[0] if ranked else DEFAULT_LANGUAGE

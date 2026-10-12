"""Detect the language of input text with langdetect."""

import logging

from langdetect import DetectorFactory, LangDetectException, detect
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


def detect_language(text: str) -> str:
    """Return the ISO 639-1 code of text, e.g. "en", "hi".

    Falls back to "en" when there is nothing to detect from (empty text,
    or only digits and symbols).
    """
    try:
        # langdetect returns region variants for some languages ("zh-cn").
        return detect(text).split("-")[0]
    except LangDetectException:
        logger.debug("Language detection failed; using %s", DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE

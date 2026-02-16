"""Feature extraction pipeline for the Translation Request Profiler."""
import re
import string
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np


# ── Unicode Normalization for Indic Scripts ──────────────────────────

def normalize_unicode(text: str) -> str:
    """Normalize Unicode text for Indic scripts.

    Uses NFC (Canonical Decomposition, followed by Canonical Composition)
    normalization which is recommended for Indic scripts.

    Args:
        text: Input text to normalize

    Returns:
        Normalized text
    """
    return unicodedata.normalize('NFC', text)


def detect_script(text: str) -> str:
    """Detect the primary script of the text.

    Args:
        text: Input text to analyze

    Returns:
        Script name (e.g., 'devanagari', 'bengali', 'tamil', 'telugu', 'latin')
    """
    if not text:
        return 'unknown'

    # Count characters by script
    script_counts = Counter()
    for char in text:
        if char.isalpha():
            try:
                char_name = unicodedata.name(char)
                # Extract script from character name
                if 'DEVANAGARI' in char_name:
                    script_counts['devanagari'] += 1
                elif 'BENGALI' in char_name:
                    script_counts['bengali'] += 1
                elif 'TAMIL' in char_name:
                    script_counts['tamil'] += 1
                elif 'TELUGU' in char_name:
                    script_counts['telugu'] += 1
                elif 'GUJARATI' in char_name:
                    script_counts['gujarati'] += 1
                elif 'KANNADA' in char_name:
                    script_counts['kannada'] += 1
                elif 'MALAYALAM' in char_name:
                    script_counts['malayalam'] += 1
                elif 'GURMUKHI' in char_name:
                    script_counts['gurmukhi'] += 1
                elif 'ORIYA' in char_name:
                    script_counts['oriya'] += 1
                elif 'ARABIC' in char_name:
                    script_counts['arabic'] += 1
                elif 'LATIN' in char_name:
                    script_counts['latin'] += 1
                else:
                    script_counts['other'] += 1
            except:
                continue

    if not script_counts:
        return 'unknown'

    # Return most common script
    return script_counts.most_common(1)[0][0]


# ── 1. Length Features ────────────────────────────────────────────────


@dataclass
class LengthFeatures:
    """Length-based features of text."""

    char_count: int
    word_count: int
    sentence_count: int
    avg_sentence_len: float
    bucket: str  # SHORT | MEDIUM | LONG


def extract_length(text: str) -> LengthFeatures:
    """Extract length-based features from text.

    Args:
        text: Input text to analyze

    Returns:
        LengthFeatures with character, word, and sentence counts
    """
    # Normalize Unicode for Indic scripts
    text = normalize_unicode(text)

    words = text.split()
    # Use regex for sentence boundary detection (supports both Western and Indic punctuation)
    # Indic languages use । (Devanagari danda) as sentence terminator
    sentences = [s.strip() for s in re.split(r'[.!?।]+', text) if s.strip()]
    word_count = len(words)
    sent_count = max(len(sentences), 1)

    if word_count <= 20:
        bucket = "SHORT"
    elif word_count <= 150:
        bucket = "MEDIUM"
    else:
        bucket = "LONG"

    return LengthFeatures(
        char_count=len(text),
        word_count=word_count,
        sentence_count=sent_count,
        avg_sentence_len=round(word_count / sent_count, 2),
        bucket=bucket,
    )


# ── 2. Language Features ─────────────────────────────────────────────


@dataclass
class LanguageFeatures:
    """Language detection features."""

    primary: str  # ISO 639-1 code
    num_languages: int
    mix_ratio: float  # 0.0 = monolingual, 1.0 = fully mixed
    language_switches: int


def extract_language(
    text: str, model_path: Optional[Path] = None
) -> LanguageFeatures:
    """Extract language detection features using langdetect library.

    Args:
        text: Input text to analyze
        model_path: Optional path (kept for backward compatibility, not used)

    Returns:
        LanguageFeatures with language detection results
    """
    try:
        from langdetect import detect, LangDetectException
    except ImportError:
        # Fallback: assume English if langdetect not available
        return LanguageFeatures(
            primary="en",
            num_languages=1,
            mix_ratio=0.0,
            language_switches=0,
        )

    # Detect at sentence level for mix detection
    sentences = [s.strip() for s in re.split(r'[.!?।॥]+', text) if len(s.strip()) > 5]
    if not sentences:
        sentences = [text]

    langs = []
    for sent in sentences:
        try:
            # langdetect returns language code directly (e.g., 'hi', 'en', 'bn')
            lang = detect(sent.replace('\n', ' '))
            langs.append(lang)
        except LangDetectException:
            # If detection fails for a sentence, skip it
            continue

    # If no languages detected, fallback to English
    if not langs:
        return LanguageFeatures(
            primary="en",
            num_languages=1,
            mix_ratio=0.0,
            language_switches=0,
        )

    lang_counts = Counter(langs)
    primary = lang_counts.most_common(1)[0][0]
    total = len(langs)

    # Mix ratio: 1 - (primary_count / total)
    mix_ratio = round(1.0 - (lang_counts[primary] / total), 2) if total > 0 else 0.0

    # Count language switches (transitions between different languages)
    switches = sum(1 for i in range(1, len(langs)) if langs[i] != langs[i - 1])

    return LanguageFeatures(
        primary=primary,
        num_languages=len(lang_counts),
        mix_ratio=mix_ratio,
        language_switches=switches,
    )


# ── 3. Structure Features ────────────────────────────────────────────


@dataclass
class StructureFeatures:
    """Structural features of text."""

    punctuation_ratio: float
    special_char_ratio: float
    digit_ratio: float
    uppercase_ratio: float


def extract_structure(text: str) -> StructureFeatures:
    """Extract structural features from text.

    Args:
        text: Input text to analyze

    Returns:
        StructureFeatures with punctuation, special chars, digits, uppercase ratios
    """
    n = max(len(text), 1)
    punct_count = sum(1 for c in text if c in string.punctuation)
    special_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
    digit_count = sum(1 for c in text if c.isdigit())
    upper_count = sum(1 for c in text if c.isupper())

    return StructureFeatures(
        punctuation_ratio=round(punct_count / n, 4),
        special_char_ratio=round(special_count / n, 4),
        digit_ratio=round(digit_count / n, 4),
        uppercase_ratio=round(upper_count / n, 4),
    )


# ── 4. Terminology Features ──────────────────────────────────────────

# Rare words = words not in the top 10k most common English words
COMMON_WORDS: Set[str] = set()


@dataclass
class TerminologyFeatures:
    """Terminology and vocabulary features."""

    avg_word_length: float
    unique_ratio: float
    rare_word_ratio: float
    long_word_ratio: float  # words > 10 chars


def load_common_words(path: Path = Path("data/common_words_10k.txt")) -> None:
    """Load common words list into global set.

    Args:
        path: Path to common words file (one word per line)
    """
    global COMMON_WORDS
    if path.exists():
        with open(path) as f:
            COMMON_WORDS = {line.strip().lower() for line in f if line.strip()}
    else:
        # If file doesn't exist, use empty set (all words considered rare)
        COMMON_WORDS = set()


def extract_terminology(text: str) -> TerminologyFeatures:
    """Extract terminology and vocabulary features.

    Args:
        text: Input text to analyze

    Returns:
        TerminologyFeatures with word length and rarity metrics
    """
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    if not words:
        return TerminologyFeatures(0.0, 0.0, 0.0, 0.0)

    n = len(words)
    lower_words = [w.lower() for w in words]

    rare_count = 0
    if COMMON_WORDS:
        rare_count = sum(1 for w in lower_words if w not in COMMON_WORDS)
    else:
        # If no common words loaded, estimate based on word length
        rare_count = sum(1 for w in words if len(w) > 8)

    return TerminologyFeatures(
        avg_word_length=round(sum(len(w) for w in words) / n, 2),
        unique_ratio=round(len(set(lower_words)) / n, 4),
        rare_word_ratio=round(rare_count / n, 4),
        long_word_ratio=round(sum(1 for w in words if len(w) > 10) / n, 4),
    )


# ── 5. Entity Features ───────────────────────────────────────────────

_nlp: Optional[object] = None


@dataclass
class EntityFeatures:
    """Named entity features."""

    entity_count: int
    entity_density: float
    entity_types: Dict[str, int]  # e.g., {"PERSON": 3, "ORG": 2}


def _get_spacy_model(model_name: str = "en_core_web_sm"):
    """Lazy-load spaCy model (singleton pattern).

    Args:
        model_name: Name of spaCy model to load

    Returns:
        Loaded spaCy model or None if not available
    """
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(model_name, disable=["parser", "lemmatizer", "tagger"])
        except (ImportError, OSError):
            # Model not available - will use fallback
            return None
    return _nlp


def extract_entities(text: str) -> EntityFeatures:
    """Extract named entity features.

    Args:
        text: Input text to analyze

    Returns:
        EntityFeatures with entity counts and types
    """
    # Normalize Unicode for Indic scripts
    text = normalize_unicode(text)

    nlp = _get_spacy_model()

    if nlp is None:
        # Fallback: simple heuristic-based entity detection
        # Works for both Latin and Indic scripts
        word_count = max(len(text.split()), 1)

        # For Indic scripts, use a simpler heuristic based on word length
        # Longer words are more likely to be named entities
        words = text.split()
        potential_entities = sum(1 for w in words if len(w) > 6)

        # Also count capitalized words for Latin script
        capitalized = len(re.findall(r'\b[A-Z][a-z]+\b', text))

        entity_count = max(potential_entities, capitalized)

        return EntityFeatures(
            entity_count=entity_count,
            entity_density=round(entity_count / word_count, 4),
            entity_types={"UNKNOWN": entity_count},
        )

    # Process with max length guard
    doc = nlp(text[:100_000])  # spaCy default max is 1M chars
    ents = doc.ents

    word_count = max(len(text.split()), 1)
    type_counts: Dict[str, int] = {}
    for ent in ents:
        type_counts[ent.label_] = type_counts.get(ent.label_, 0) + 1

    return EntityFeatures(
        entity_count=len(ents),
        entity_density=round(len(ents) / word_count, 4),
        entity_types=type_counts,
    )


# ── 6. Combined Feature Vector (for ML models) ──────────────────────


def extract_numeric_features(text: str) -> np.ndarray:
    """Extract all numeric features as a flat vector for ML models.

    Args:
        text: Input text to analyze

    Returns:
        NumPy array of numeric features
    """
    # Normalize Unicode for Indic scripts at the start
    text = normalize_unicode(text)

    length = extract_length(text)
    structure = extract_structure(text)
    terminology = extract_terminology(text)
    entities = extract_entities(text)
    language = extract_language(text)

    return np.array([
        length.char_count,
        length.word_count,
        length.sentence_count,
        length.avg_sentence_len,
        structure.punctuation_ratio,
        structure.special_char_ratio,
        structure.digit_ratio,
        structure.uppercase_ratio,
        terminology.avg_word_length,
        terminology.unique_ratio,
        terminology.rare_word_ratio,
        terminology.long_word_ratio,
        entities.entity_count,
        entities.entity_density,
        language.num_languages,
        language.mix_ratio,
        language.language_switches,
    ])


FEATURE_NAMES = [
    "char_count",
    "word_count",
    "sentence_count",
    "avg_sentence_len",
    "punctuation_ratio",
    "special_char_ratio",
    "digit_ratio",
    "uppercase_ratio",
    "avg_word_length",
    "unique_ratio",
    "rare_word_ratio",
    "long_word_ratio",
    "entity_count",
    "entity_density",
    "num_languages",
    "mix_ratio",
    "language_switches",
]


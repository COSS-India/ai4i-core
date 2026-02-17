"""Main profiler orchestration - combines feature extraction and ML models."""
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import settings
from .errors import (
    ModelError,
    ModelNotLoadedError,
    ValidationError,
    handle_model_error,
    retry_with_backoff,
    safe_execute,
    validate_input
)

logger = logging.getLogger(__name__)
from .features import (
    extract_entities,
    extract_language,
    extract_length,
    extract_numeric_features,
    extract_structure,
    extract_terminology,
    load_common_words,
)
from .schemas import (
    DomainPrediction,
    DomainProfile,
    LanguageProfile,
    LengthProfile,
    ProfileResult,
    ScoresProfile,
    StructureProfile,
)


class RequestProfiler:
    """Main profiler class that orchestrates feature extraction and ML predictions."""

    def __init__(self):
        """Initialize profiler with models."""
        self.domain_model = None
        self.complexity_model = None
        self.models_loaded = False
        self.model_version = "2.0.0"
        self.load_attempts = 0
        self.max_load_attempts = 3

    @retry_with_backoff(max_retries=2, initial_delay=1.0, exceptions=(FileNotFoundError, IOError))
    def load_models(self) -> None:
        """
        Load all required models with retry logic and comprehensive error handling.

        Raises:
            ModelError: If models cannot be loaded after retries
        """
        import joblib

        self.load_attempts += 1
        logger.info(f"Loading models (attempt {self.load_attempts}/{self.max_load_attempts})...")

        try:
            # Validate model paths exist
            if not settings.domain_model_path or not settings.domain_model_path.exists():
                raise FileNotFoundError(
                    f"Domain model not found at: {settings.domain_model_path}"
                )

            if not settings.complexity_model_path or not settings.complexity_model_path.exists():
                raise FileNotFoundError(
                    f"Complexity model not found at: {settings.complexity_model_path}"
                )

            # Load domain classifier
            logger.info(f"Loading domain classifier from {settings.domain_model_path}")
            self.domain_model = joblib.load(settings.domain_model_path)

            # Validate model has required methods
            if not hasattr(self.domain_model, 'predict_proba'):
                raise ModelError(
                    "Domain model missing required 'predict_proba' method",
                    recoverable=False
                )

            # Load complexity regressor
            logger.info(f"Loading complexity regressor from {settings.complexity_model_path}")
            self.complexity_model = joblib.load(settings.complexity_model_path)

            # Validate model has required methods
            if not hasattr(self.complexity_model, 'predict'):
                raise ModelError(
                    "Complexity model missing required 'predict' method",
                    recoverable=False
                )

            # Load common words for terminology features (optional)
            if settings.common_words_path.exists():
                logger.info(f"Loading common words from {settings.common_words_path}")
                load_common_words(settings.common_words_path)
            else:
                logger.warning(f"Common words file not found: {settings.common_words_path}")

            self.models_loaded = True
            logger.info(f"✓ Models loaded successfully (version {self.model_version})")

        except FileNotFoundError as e:
            logger.error(f"Model file not found: {e}")
            raise ModelError(
                f"Required model files not found: {e}",
                details={"model_dir": str(settings.model_dir)},
                recoverable=True
            )
        except Exception as e:
            logger.error(f"Failed to load models: {e}", exc_info=True)
            raise ModelError(
                f"Failed to load models: {e}",
                details={"error_type": type(e).__name__},
                recoverable=False
            )

    @handle_model_error
    def profile(
        self,
        text: str,
        include_entities: bool = True,
        include_language: bool = True
    ) -> ProfileResult:
        """
        Profile a single text and return complete analysis with comprehensive error handling.

        Args:
            text: Input text to profile
            include_entities: Whether to extract named entities
            include_language: Whether to perform language detection

        Returns:
            ProfileResult with all profiling information

        Raises:
            ModelNotLoadedError: If models are not loaded
            ValidationError: If input validation fails
            ModelError: If profiling fails
        """
        # Validate models are loaded
        if not self.models_loaded:
            logger.error("Attempted to profile text before models were loaded")
            raise ModelNotLoadedError()

        # Validate input
        validate_input(text, min_length=1, max_length=100000)

        try:
            logger.debug(f"Profiling text of length {len(text)}")

            # Extract features with safe execution
            length_features = safe_execute(
                extract_length, text,
                default=None,
                log_errors=True
            )

            structure_features = safe_execute(
                extract_structure, text,
                default=None,
                log_errors=True
            )

            terminology_features = safe_execute(
                extract_terminology, text,
                default=None,
                log_errors=True
            )

            # Check if core features extracted successfully
            if not all([length_features, structure_features, terminology_features]):
                raise ModelError(
                    "Failed to extract core features from text",
                    details={"text_length": len(text)}
                )

            # Optional features with graceful degradation
            entity_features = None
            if include_entities:
                entity_features = safe_execute(
                    extract_entities, text,
                    default=None,
                    log_errors=True
                )

            language_features = None
            if include_language:
                language_features = safe_execute(
                    extract_language, text,
                    default=None,
                    log_errors=True
                )

            # Domain classification with error handling
            try:
                domain_probs = self.domain_model.predict_proba([text])[0]
                domain_classes = self.domain_model.classes_

                # Get top 3 predictions
                top_3_indices = np.argsort(domain_probs)[-3:][::-1]
                top_3 = [
                    DomainPrediction(
                        label=domain_classes[i],
                        confidence=round(float(domain_probs[i]), 4)
                    )
                    for i in top_3_indices
                ]

                domain_profile = DomainProfile(
                    label=domain_classes[np.argmax(domain_probs)],
                    confidence=round(float(np.max(domain_probs)), 4),
                    top_3=top_3,
                )
            except Exception as e:
                logger.error(f"Domain classification failed: {e}")
                raise ModelError(
                    f"Domain classification failed: {e}",
                    details={"model": "domain_classifier"}
                )

            # Complexity prediction with error handling
            try:
                numeric_features = extract_numeric_features(text)
                complexity_score = float(self.complexity_model.predict([numeric_features])[0])
                complexity_score = max(0.0, min(1.0, complexity_score))  # Clamp to [0, 1]

                # Determine complexity level (2-tier system: LOW or HIGH)
                # Cutoff at 0.5: scores < 0.5 are LOW, scores >= 0.5 are HIGH
                if complexity_score < 0.5:
                    complexity_level = "LOW"
                else:
                    complexity_level = "HIGH"

                # Feature contributions (from RandomForest feature importances)
                feature_importances = self.complexity_model.feature_importances_
                top_features_idx = np.argsort(feature_importances)[-3:][::-1]
            except Exception as e:
                logger.error(f"Complexity prediction failed: {e}")
                raise ModelError(
                    f"Complexity prediction failed: {e}",
                    details={"model": "complexity_regressor"}
                )

            # Build feature contributions
            try:
                from .features import FEATURE_NAMES
                feature_contributions = {
                    FEATURE_NAMES[i]: round(float(feature_importances[i]), 4)
                    for i in top_features_idx
                }
            except Exception as e:
                logger.warning(f"Failed to extract feature contributions: {e}")
                feature_contributions = {}

            # Build response with safe defaults
            try:
                return ProfileResult(
                    length=LengthProfile(
                        char_count=length_features.char_count,
                        word_count=length_features.word_count,
                        sentence_count=length_features.sentence_count,
                        avg_sentence_len=length_features.avg_sentence_len,
                            bucket=length_features.bucket,
                    ),
                    language=LanguageProfile(
                        primary=language_features.primary if language_features else "en",
                        num_languages=language_features.num_languages if language_features else 1,
                        mix_ratio=language_features.mix_ratio if language_features else 0.0,
                        language_switches=language_features.language_switches if language_features else 0,
                    ),
                    domain=domain_profile,
                    structure=StructureProfile(
                        entity_density=entity_features.entity_density if entity_features else 0.0,
                        terminology_density=terminology_features.rare_word_ratio if terminology_features else 0.0,
                        numeric_density=structure_features.digit_ratio if structure_features else 0.0,
                        entity_types=entity_features.entity_types if entity_features else {},
                    ),
                    scores=ScoresProfile(
                        complexity_score=round(complexity_score, 4),
                        complexity_level=complexity_level,
                        feature_contributions=feature_contributions,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to build ProfileResult: {e}")
                raise ModelError(
                    f"Failed to build profile result: {e}",
                    details={"error_type": type(e).__name__}
                )

        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except ModelError:
            # Re-raise model errors as-is
            raise
        except Exception as e:
            # Catch any unexpected errors
            logger.error(f"Unexpected error during profiling: {e}", exc_info=True)
            raise ModelError(
                f"Unexpected profiling error: {e}",
                details={"error_type": type(e).__name__}
            )


# Global profiler instance
profiler = RequestProfiler()


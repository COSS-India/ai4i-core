"""Run a PII policy against sample text (the Playground "Run Simulation").

A policy is the list of policy_type rows it references, in the shape
platform-core-service stores them (policy_type.policy_fields JSONB):

    custom_field:          [{entity_name, regex, examples}]  -> regex recognizer
    model_supported_field: [{<lang>: [{entity_name}]}]       -> Presidio's built-in
                                                                 recognizers / spaCy NER

The text's language is detected (services/pii/language.py); it picks the
spaCy model and the model_supported_field list. Only the policy's entities
are detected. Each detection is replaced with a
numbered token by the entity_counter operator. Per-type actions (mask,
redact, hash) are not part of policy_fields yet, so they are not applied.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import regex
from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult

from services.pii.engine import get_engine
from services.pii.language import detect_language
from services.pii.model_registry import get_spacy_lang_code

# Score for policy regex matches. Policy regexes are explicit admin config,
# so Presidio prefers them over spaCy NER guesses (0.85) on the same span.
CUSTOM_FIELD_SCORE = 1.0

# Presidio's default flags include IGNORECASE; policy regexes such as IFSC
# ([A-Z]{4}0...) and PAN rely on case, so match them as written.
CUSTOM_FIELD_REGEX_FLAGS = regex.MULTILINE | regex.DOTALL

# Time limit for one policy regex over one text. A regex with catastrophic
# backtracking is cut off here instead of holding a worker thread.
REGEX_TIMEOUT_SECONDS = 1.0


class InvalidPolicyError(ValueError):
    """The policy's fields cannot be turned into recognizers."""


class RegexTimeoutError(InvalidPolicyError):
    """A policy regex ran longer than REGEX_TIMEOUT_SECONDS."""


@dataclass
class CustomField:
    entity_name: str
    regex: str


@dataclass
class PolicyType:
    name: str
    custom_fields: List[CustomField] = field(default_factory=list)
    # language code -> entity names for Presidio's built-in recognizers
    model_entities: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class DetectedType:
    entity_type: str
    policy_type: str
    instances: int = 0
    # original value -> token, in order of first appearance
    replacements: Dict[str, str] = field(default_factory=dict)


@dataclass
class SimulationResult:
    sanitized_text: str
    detected: List[DetectedType]


class TimedPatternRecognizer(PatternRecognizer):
    """PatternRecognizer that stops a regex after a time limit.

    Presidio matches with regex.finditer and no timeout. These regexes come
    from the request, so one with catastrophic backtracking ("(a|aa)+$")
    would otherwise hold a worker thread indefinitely.
    """

    def __init__(self, *, timeout: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self._timeout = timeout
        # Raises regex.error for an invalid pattern.
        self._compiled = [
            (pattern, regex.compile(pattern.regex, self.global_regex_flags))
            for pattern in self.patterns
        ]

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
        regex_flags: Optional[int] = None,
    ) -> List[RecognizerResult]:
        results = []
        for pattern, compiled in self._compiled:
            try:
                spans = [m.span() for m in compiled.finditer(text, timeout=self._timeout)]
            except TimeoutError as exc:
                raise RegexTimeoutError(
                    f"{self.name}: regex took longer than {self._timeout}s on this text."
                ) from exc
            for start, end in spans:
                if start == end:
                    continue
                results.append(
                    RecognizerResult(
                        entity_type=self.supported_entities[0],
                        start=start,
                        end=end,
                        score=pattern.score,
                        analysis_explanation=self.build_regex_explanation(
                            self.name, pattern.name, pattern.regex, pattern.score, None,
                            self.global_regex_flags,
                        ),
                        recognition_metadata={
                            RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                            RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                        },
                    )
                )
        return EntityRecognizer.remove_duplicates(results)


def _build_recognizers(
    policy_types: List[PolicyType], language: str
) -> tuple[List[PatternRecognizer], Dict[str, str]]:
    """Return the ad-hoc recognizers and {entity_type: policy_type name}."""
    lang_code = get_spacy_lang_code(language)
    recognizers: List[PatternRecognizer] = []
    entity_source: Dict[str, str] = {}

    for pt in policy_types:
        for cf in pt.custom_fields:
            try:
                recognizers.append(
                    TimedPatternRecognizer(
                        timeout=REGEX_TIMEOUT_SECONDS,
                        supported_entity=cf.entity_name,
                        name=f"{pt.name}:{cf.entity_name}",
                        supported_language=lang_code,
                        patterns=[Pattern(cf.entity_name, cf.regex, CUSTOM_FIELD_SCORE)],
                        global_regex_flags=CUSTOM_FIELD_REGEX_FLAGS,
                    )
                )
            except regex.error as exc:
                raise InvalidPolicyError(
                    f"{pt.name}: invalid regex for {cf.entity_name}: {exc}"
                ) from exc
            entity_source.setdefault(cf.entity_name, pt.name)

        for entity in pt.model_entities.get(language, []):
            entity_source.setdefault(entity, pt.name)

    return recognizers, entity_source


def simulate(text: str, policy_types: List[PolicyType]) -> SimulationResult:
    language = detect_language(text)
    recognizers, entity_source = _build_recognizers(policy_types, language)
    if not entity_source or not text.strip():
        # entities=[] would mean "all entities" to Presidio; a policy with no
        # PII types must detect nothing.
        return SimulationResult(text, [])

    engine = get_engine()
    analyzer_results = engine.analyze(
        text, language, entities=list(entity_source), ad_hoc_recognizers=recognizers
    )
    anonymized, entity_mapping = engine.anonymize(text, analyzer_results)

    token_to_value = {
        token: value for per_type in entity_mapping.values() for value, token in per_type.items()
    }
    detected: Dict[str, DetectedType] = {}
    # Presidio returns items right to left; report them in reading order.
    for item in sorted(anonymized.items, key=lambda i: i.start):
        row = detected.setdefault(
            item.entity_type,
            DetectedType(item.entity_type, entity_source.get(item.entity_type, "")),
        )
        row.instances += 1
        row.replacements.setdefault(token_to_value[item.text], item.text)

    return SimulationResult(sanitized_text=anonymized.text, detected=list(detected.values()))

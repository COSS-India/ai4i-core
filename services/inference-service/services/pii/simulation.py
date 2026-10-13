"""Run a PII policy against sample text (the Playground "Run Simulation").

A policy is the list of policy_type rows it references. routes/pii.py
flattens each row's policy_fields (keyed by domain, e.g. "Finance") and
passes the result here as PolicyType:

    custom_field:          [{entity_name, regex}]   -> regex recognizer
    model_supported_field: [{<lang>: [{entity_name}]}] -> Presidio's built-in
                                                         recognizers / spaCy NER

The text's language is detected among the languages the policy lists in
model_supported_field (services/pii/language.py); it picks the spaCy model
and the model_supported_field list. Only the policy's entities are detected.
Each detection is replaced with a numbered token by the entity_counter operator. Per-type actions (mask,
redact, hash) are not part of policy_fields yet, so they are not applied.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import regex
from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult

from services.pii.engine import get_engine
from services.pii.language import DEFAULT_LANGUAGE, detect_language
from services.pii.model_registry import get_spacy_lang_code

# Score for policy regex matches. Policy regexes are explicit admin config,
# so Presidio prefers them over spaCy NER guesses (0.85) on the same span.
CUSTOM_FIELD_SCORE = 1.0

# Presidio's default flags include IGNORECASE; policy regexes such as IFSC
# ([A-Z]{4}0...) and PAN rely on case, so match them as written.
CUSTOM_FIELD_REGEX_FLAGS = regex.MULTILINE | regex.DOTALL

# Total time all of one request's policy regexes may take. A per-pattern
# limit is not enough: a request can carry thousands of patterns.
REGEX_BUDGET_SECONDS = 2.0


class InvalidPolicyError(ValueError):
    """The policy's fields cannot be turned into recognizers."""


class RegexTimeoutError(InvalidPolicyError):
    """The request's policy regexes ran past REGEX_BUDGET_SECONDS."""


class RegexBudget:
    """One deadline shared by every policy regex in a request.

    The clock starts at the first regex, so spaCy's processing of the text
    (which runs before the recognizers) does not use up the budget.
    """

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._deadline: Optional[float] = None

    def remaining(self) -> float:
        if self._deadline is None:
            self._deadline = time.monotonic() + self.seconds
        return self._deadline - time.monotonic()


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
    # every policy type that defines this entity, in request order
    policy_types: List[str]
    instances: int = 0
    # original value -> token, in order of first appearance
    replacements: Dict[str, str] = field(default_factory=dict)


@dataclass
class SimulationResult:
    sanitized_text: str
    detected: List[DetectedType]


class TimedPatternRecognizer(PatternRecognizer):
    """PatternRecognizer whose regexes stop when the request's budget runs out.

    Presidio matches with regex.finditer and no timeout. These regexes come
    from the request, so one with catastrophic backtracking ("(a|aa)+$")
    would otherwise hold a worker thread indefinitely.
    """

    def __init__(self, *, budget: RegexBudget, **kwargs) -> None:
        super().__init__(**kwargs)
        self._budget = budget
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
            remaining = self._budget.remaining()
            try:
                if remaining <= 0:
                    raise TimeoutError
                spans = [m.span() for m in compiled.finditer(text, timeout=remaining)]
            except TimeoutError as exc:
                raise RegexTimeoutError(
                    f"{self.name}: the policy's regexes took longer than "
                    f"{self._budget.seconds}s in total on this text."
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


@dataclass
class _Recognizers:
    ad_hoc: List[PatternRecognizer]
    # entity -> every policy type that defines it (custom or model field)
    sources: Dict[str, List[str]]
    # entities listed in model_supported_field for the detected language
    model_entities: Set[str]


def _add_source(sources: Dict[str, List[str]], entity: str, policy_type: str) -> None:
    names = sources.setdefault(entity, [])
    if policy_type not in names:
        names.append(policy_type)


def _build_recognizers(policy_types: List[PolicyType], language: str) -> _Recognizers:
    lang_code = get_spacy_lang_code(language)
    budget = RegexBudget(REGEX_BUDGET_SECONDS)
    recognizers: List[PatternRecognizer] = []
    sources: Dict[str, List[str]] = {}
    model_entities: Set[str] = set()

    for pt in policy_types:
        for cf in pt.custom_fields:
            try:
                recognizers.append(
                    TimedPatternRecognizer(
                        budget=budget,
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
            _add_source(sources, cf.entity_name, pt.name)

        for entity in pt.model_entities.get(language, []):
            model_entities.add(entity)
            _add_source(sources, entity, pt.name)

    return _Recognizers(recognizers, sources, model_entities)


def simulate(text: str, policy_types: List[PolicyType]) -> SimulationResult:
    # Only languages the policy configures can change the result; restricting
    # detection to them avoids short English text being read as "et" or "nl".
    policy_languages = {lang for pt in policy_types for lang in pt.model_entities}
    language = detect_language(text, policy_languages) if policy_languages else DEFAULT_LANGUAGE
    recs = _build_recognizers(policy_types, language)
    if not recs.sources or not text.strip():
        # entities=[] would mean "all entities" to Presidio; a policy with no
        # PII types must detect nothing.
        return SimulationResult(text, [])

    engine = get_engine()
    if recs.model_entities:
        undetectable = recs.model_entities - engine.detectable_entities(language)
        if undetectable:
            # Presidio would raise "No matching recognizers" (a 500) or find
            # nothing, and the Playground would report "no PII".
            raise InvalidPolicyError(
                f"model_supported_field entities that cannot be detected in "
                f"'{language}' text: {', '.join(sorted(undetectable))}. Use a "
                f"custom_field regex instead, or remove them for this language."
            )

    # Policy regexes run on their own and Presidio only for the
    # model_supported_field entities, so a built-in recognizer (EmailRecognizer
    # for a custom EMAIL_ADDRESS) never competes with the policy's regex on the
    # same span.
    analyzer_results = [
        result for recognizer in recs.ad_hoc
        for result in recognizer.analyze(text, recognizer.supported_entities)
    ]
    if recs.model_entities:
        analyzer_results += engine.analyze(text, language, entities=sorted(recs.model_entities))
    anonymized, entity_mapping = engine.anonymize(text, analyzer_results)

    token_to_value = {
        token: value for per_type in entity_mapping.values() for value, token in per_type.items()
    }
    detected: Dict[str, DetectedType] = {}
    # Presidio returns items right to left; report them in reading order.
    for item in sorted(anonymized.items, key=lambda i: i.start):
        row = detected.setdefault(
            item.entity_type,
            DetectedType(item.entity_type, recs.sources.get(item.entity_type, [])),
        )
        row.instances += 1
        row.replacements.setdefault(token_to_value[item.text], item.text)

    return SimulationResult(sanitized_text=anonymized.text, detected=list(detected.values()))

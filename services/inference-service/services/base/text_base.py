"""
TextBase — base class for all text-backed inference services.

Item presence (each item needs a 'source') is declared via REQUIRED_ITEM_FIELDS
and checked by the generic BaseTaskService.validate_request. TextBase overrides
validate_request to add the text config rule (a 'config' block, and a
sourceLanguage when a language block is supplied). Services that translate (NMT,
Transliteration) extend TranslationTextBase, which adds the source/target rule.

The module-level NER BPE-to-word alignment functions at the bottom are pure
helpers imported and used by ner_service (kept here by request so the service
file holds only its post_process orchestration).
"""

from typing import Any, Dict
from services.base.task_service import BaseTaskService


# ----------------------------------------------------------------------------
# Stateless text helpers (sanitisation, normalisation, chunking).
#
# Pure functions, no task state — text services compose these instead of
# re-implementing them. Module-level (not TextBase methods) so TTS, which
# expands text into chunks before inference, can reuse chunk_text without an
# instance.
# ----------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return " ".join(text.split()).strip()


def sanitize_source(text: object) -> str:
    """Return a single-line, whitespace-normalised source string.

    Falsy input becomes a single space (Triton text models reject empty
    strings); newlines and carriage returns are flattened to spaces before
    normalisation. Never returns an empty string.
    """
    if not text:
        return " "
    text = str(text).replace("\n", " ").replace("\r", " ")
    return normalize_text(text) or " "


def chunk_text(text: str, max_length: int) -> list:
    """Split text into chunks of at most max_length characters.

    Splits at the nearest sentence or clause boundary (., ?, !, Devanagari
    danda, comma, space) before max_length, falling back to a hard cut.
    Empty input yields a single empty chunk; empty pieces are dropped.
    """
    text = normalize_text(text)
    if not text:
        return [""]
    if len(text) <= max_length:
        return [text]

    chunks: list = []
    while len(text) > max_length:
        split_pos = max_length
        for sep in (".", "?", "!", "।", ",", " "):
            pos = text.rfind(sep, 0, max_length)
            if pos > 0:
                split_pos = pos + 1
                break
        chunks.append(text[:split_pos].strip())
        text = text[split_pos:].strip()

    if text:
        chunks.append(text)
    return [c for c in chunks if c]


class TextBase(BaseTaskService):
    payload_key = "input"  # text input list lives under payload['input']

    # Each text item must carry a non-empty 'source'.
    REQUIRED_ITEM_FIELDS = (("source",),)

    # ------------------------------------------------------------------
    # Validation (item presence is generic; text adds the config rule)
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """Generic item presence (super) plus the text config rule: a 'config'
        block must be present, and when a language block is supplied it must
        carry a sourceLanguage. Translating services extend TranslationTextBase,
        which adds the source/target rule."""
        await super().validate_request(payload)

        if not payload.get("config"):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

        language = self._get_nested(payload, "config.language")
        if language and not self._get_nested(payload, "config.language.sourceLanguage"):
            raise ValueError(f"{self.task_name}: config.language.sourceLanguage is required")

    # ------------------------------------------------------------------
    # preprocess_input
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_data = payload.get(self.payload_key) or []
        source_texts = self.extract_field_from_items(input_data, "source")
        sanitized = [sanitize_source(t) for t in source_texts]

        items = [
            {**item, "source": sanitized[idx] if idx < len(sanitized) else ""}
            for idx, item in enumerate(input_data)
        ]

        payload[self.payload_key] = items
        return payload


class TranslationTextBase(TextBase):
    """Base for text services that translate between a source and target
    language (NMT, Transliteration). Adds the required, distinct source/target
    rule on top of the TextBase config checks, so a leaf service declares the
    requirement by extending this class rather than via a flag or a per-service
    validate_request override."""

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """Text rules (super) plus a required, distinct source and target language."""
        await super().validate_request(payload)
        source = self._get_nested(payload, "config.language.sourceLanguage")
        target = self._get_nested(payload, "config.language.targetLanguage")
        if not source:
            raise ValueError(f"{self.task_name}: config.language.sourceLanguage is required")
        if not target:
            raise ValueError(f"{self.task_name}: config.language.targetLanguage is required")
        if source == target:
            raise ValueError(f"{self.task_name}: sourceLanguage and targetLanguage cannot be the same")


# ----------------------------------------------------------------------------
# NER BPE-to-word alignment (pure helpers; imported by ner_service)
#
# These map a model's BPE entity predictions onto the original words with
# character offsets. They are NER-specific and live here only so the service
# file stays thin; nothing else in this module uses them.
# ----------------------------------------------------------------------------

def ner_entity(pred: Dict[str, Any]) -> str:
    return str(pred.get("entity") or pred.get("token") or "")


def ner_tag(pred: Dict[str, Any]) -> str:
    for k in ("class", "tag", "label", "entity_type"):
        v = pred.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return "O"


def build_word_positions(source: str) -> list:
    positions, pos = [], 0
    for word in source.split():
        start = source.find(word, pos)
        positions.append({"word": word, "start": start, "end": start + len(word)})
        pos = start + len(word)
    return positions


def _merge_bpe(preds: list, start: int, end: int) -> str:
    parts = []
    for i in range(start, end):
        p = ner_entity(preds[i])
        parts.append(p[2:] if p.startswith("##") else p)
    return (parts[0] + "".join(parts[1:])).strip() if parts else ""


def group_bpe_tokens(preds: list) -> list:
    groups, i = [], 0
    while i < len(preds):
        entity = ner_entity(preds[i])
        if not entity:
            i += 1
            continue
        j = i + 1
        while j < len(preds) and ner_entity(preds[j]).startswith("##"):
            j += 1
        full = _merge_bpe(preds, i, j)
        groups.append({"tag": ner_tag(preds[i]), "entity": full,
                       "first_char": full[0].lower() if full else ""})
        i = j
    return groups


def align_tags_to_words(word_positions: list, groups: list, source: str) -> dict:
    word_to_pred, src_lower = {}, source.lower()
    for grp in groups:
        entity = (grp.get("entity") or "").strip()
        if not entity:
            continue
        ent_lower, search_pos, matched = entity.lower(), 0, False
        while True:
            s = src_lower.find(ent_lower, search_pos)
            if s < 0:
                break
            e = s + len(ent_lower)
            for wi, winfo in enumerate(word_positions):
                if winfo["start"] < e and winfo["end"] > s:
                    word_to_pred[wi] = grp
            matched = True
            search_pos = e
        if matched:
            continue
        for wi, winfo in enumerate(word_positions):
            if winfo["word"].lower() == ent_lower:
                word_to_pred[wi] = grp
    return word_to_pred


def build_ner_token_predictions(word_positions: list, aligned: dict) -> list:
    return [{"token": wi["word"], "tag": aligned[idx]["tag"] if idx in aligned else "O",
             "tokenIndex": idx, "tokenStartIndex": wi["start"], "tokenEndIndex": wi["end"]}
            for idx, wi in enumerate(word_positions)]


def flatten_ner_predictions(raw_values: list) -> list:
    """Flatten the decoded OUTPUT_TEXT values into a flat list of prediction
    items. A value may be a parsed object, a {"output": [...]} envelope, or a
    list of either; a raw string means the model returned non-JSON, which is a
    client error."""
    items = []
    for value in raw_values:
        if isinstance(value, str):
            raise ValueError(f"NER: model returned non-JSON output: {value[:80]!r}")
        if isinstance(value, dict):
            items.extend(value["output"] if "output" in value else [value])
        elif isinstance(value, list):
            items.extend(value)
    return items


def align_ner_output(items: list, sources: list) -> list:
    """Align each item's BPE entity predictions onto its source words, producing
    the ULCA NER output list ({source, nerPrediction:[...]} per item)."""
    output_list = []
    for idx, item in enumerate(items):
        source = item.get("source") or (sources[idx] if idx < len(sources) else "")
        word_positions = build_word_positions(source)
        groups = group_bpe_tokens(item.get("nerPrediction", []))
        aligned = align_tags_to_words(word_positions, groups, source)
        tokens_raw = build_ner_token_predictions(word_positions, aligned)
        ner_predictions = [
            {
                "token":           t["token"],
                "tag":             t["tag"],
                "tokenIndex":      t_idx,
                "tokenStartIndex": t["tokenStartIndex"],
                "tokenEndIndex":   t["tokenEndIndex"],
            }
            for t_idx, t in enumerate(tokens_raw)
        ]
        output_list.append({"source": source, "nerPrediction": ner_predictions})
    return output_list

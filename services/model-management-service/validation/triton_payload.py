"""Build task-aware Triton v2 ``/infer`` JSON bodies from model metadata."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _resolve_languages(languages: Optional[List[Dict[str, Any]]]) -> tuple[str, str]:
    """Pick a source/target language pair from the model's ``languages`` list."""
    if languages and isinstance(languages, list):
        for entry in languages:
            if isinstance(entry, dict):
                src = entry.get("sourceLanguage")
                tgt = entry.get("targetLanguage")
                if src and tgt:
                    return str(src), str(tgt)
        for entry in languages:
            if isinstance(entry, dict):
                lang = entry.get("sourceLanguage") or entry.get("targetLanguage")
                if lang:
                    return str(lang), str(lang)
    return "en", "hi"


def _bytes_value_for_input(name: str, source_lang: str, target_lang: str) -> str:
    """Choose a sensible string value for a BYTES-type Triton input based on its name."""
    n = name.upper()
    if "TEXT" in n or "SENTENCE" in n or "INPUT_STR" in n:
        return "validation"
    if ("LANGUAGE" in n or "LANG" in n) and ("OUTPUT" in n or "TARGET" in n or "TGT" in n):
        return target_lang
    if ("LANGUAGE" in n or "LANG" in n) and ("INPUT" in n or "SOURCE" in n or "SRC" in n):
        return source_lang
    if "LANGUAGE" in n or "LANG" in n:
        return source_lang
    return "test"


def _dummy_data(datatype: str, shape: List[int], name: str, source_lang: str, target_lang: str) -> List[Any]:
    dt = (datatype or "FP32").upper()
    count = 1
    for d in shape:
        if isinstance(d, int) and d > 0:
            count *= d

    if dt == "BYTES":
        val = _bytes_value_for_input(name, source_lang, target_lang)
        return [_b64(val)] * count
    if dt in ("FP32", "FP16", "BF16", "FP64"):
        return [0.0] * count
    if dt in ("INT32", "UINT32", "INT64", "UINT64", "INT8", "UINT8", "INT16", "UINT16"):
        return [0] * count
    if dt == "BOOL":
        return [False] * count
    return [0] * count


def _normalize_shape(shape: Any) -> List[int]:
    if not isinstance(shape, list) or not shape:
        return [1]
    return [int(d) if isinstance(d, int) and d > 0 else 1 for d in shape]


def build_triton_infer_body(
    metadata: Dict[str, Any],
    languages: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build a minimal Triton ``/v2/models/{name}/infer`` JSON body from model metadata.

    Uses input names to infer what kind of data each tensor expects (e.g. language
    codes vs free text) so the probe doesn't get rejected for nonsensical values.
    """
    inputs_meta = metadata.get("inputs")
    if not isinstance(inputs_meta, list) or not inputs_meta:
        return None

    source_lang, target_lang = _resolve_languages(languages)

    inputs: List[Dict[str, Any]] = []
    for spec in inputs_meta:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not name:
            continue
        datatype = spec.get("datatype") or "FP32"
        shape = _normalize_shape(spec.get("shape"))
        inputs.append({
            "name": name,
            "shape": shape,
            "datatype": datatype,
            "data": _dummy_data(datatype, shape, name, source_lang, target_lang),
        })

    if not inputs:
        return None

    outputs: List[Dict[str, str]] = []
    outputs_meta = metadata.get("outputs")
    if isinstance(outputs_meta, list):
        for spec in outputs_meta:
            if isinstance(spec, dict) and spec.get("name"):
                outputs.append({"name": spec["name"]})

    return {"id": "0", "inputs": inputs, "outputs": outputs}

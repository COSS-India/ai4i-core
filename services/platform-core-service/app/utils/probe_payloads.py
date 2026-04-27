"""
Probe Payload Builders for endpoint validation.

Two payload formats are supported:

* **Triton V2** — native ``{"inputs": [...], "outputs": [...]}`` for raw
  Triton Inference Server endpoints (selected when the model exposes a
  ``schema.response.triton`` block).
* **ULCA** — application-level payloads consumed by the wrapping inference
  services (nmt/asr/tts/etc.).

The unified entry point is :func:`build_probe_payload`.
"""

import base64
import io
import struct
from typing import Any, Dict, List, Optional, Tuple


# ── Minimal silent WAV (0.1s, 16 kHz mono 16-bit PCM) ──


def _make_silent_wav_b64(duration_s: float = 0.1, sample_rate: int = 16000) -> str:
    num_samples = int(sample_rate * duration_s)
    data_size = num_samples * 2
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return base64.b64encode(buf.getvalue()).decode()


MINIMAL_WAV_B64: str = _make_silent_wav_b64()
# 1×1 white RGB PNG (69 bytes)
MINIMAL_PNG_B64: str = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/"
    "AAX+Av4N70a4AAAAAElFTkSuQmCC"
)

AUDIO_INPUT_NAMES = frozenset(
    {"audio", "audio_data", "wav", "wav_data", "audio_content", "raw_audio"}
)
IMAGE_INPUT_NAMES = frozenset(
    {
        "image",
        "image_data",
        "image_content",
        "raw_image",
        "img",
        "pixels",
        "input_image",
        "image_bytes",
        "photo",
        "picture",
    }
)


# ── Triton V2 ──


_TRITON_DTYPE_DEFAULTS: Dict[str, List[Any]] = {
    "BYTES": [""],
    "FP16": [0.0],
    "FP32": [0.0],
    "FP64": [0.0],
    "BOOL": [False],
    "INT8": [0],
    "INT16": [0],
    "INT32": [0],
    "INT64": [0],
    "UINT8": [0],
    "UINT16": [0],
    "UINT32": [0],
    "UINT64": [0],
}


def _shape_dim_to_int(token: str) -> int:
    token = token.strip()
    if not token:
        return 1
    try:
        v = int(token)
        return 1 if v < 0 else max(v, 1)
    except ValueError:
        return 1


def _parse_shape(shape_raw: Any) -> List[int]:
    if isinstance(shape_raw, str):
        shape_raw = shape_raw.strip("[] ")
        parts = [p.strip() for p in shape_raw.split(",") if p.strip()]
        return [_shape_dim_to_int(p) for p in parts] or [1]
    if isinstance(shape_raw, list):
        out: List[int] = []
        for s in shape_raw:
            if isinstance(s, int):
                out.append(1 if s < 0 else max(s, 1))
            else:
                out.append(_shape_dim_to_int(str(s)))
        return out or [1]
    return [1]


def _dummy_data_for_input(name: str, datatype: str, shape: List[int]) -> list:
    """Pick a dummy tensor: silent WAV for audio BYTES, 1×1 PNG for image BYTES."""
    if datatype == "BYTES" and name:
        norm = name.lower().replace("-", "_")
        if norm in AUDIO_INPUT_NAMES:
            unit = [MINIMAL_WAV_B64]
        elif norm in IMAGE_INPUT_NAMES:
            unit = [MINIMAL_PNG_B64]
        else:
            unit = _TRITON_DTYPE_DEFAULTS.get(datatype, [""])
    else:
        unit = _TRITON_DTYPE_DEFAULTS.get(datatype, [""])
    total = 1
    for dim in shape:
        total *= max(dim, 1)
    return unit * total


def _coerce_explicit_data(explicit: Any, total: int) -> list:
    if explicit is None:
        return []
    data = explicit if isinstance(explicit, list) else [explicit]
    if total <= 0 or len(data) == 0:
        return data
    if len(data) == total:
        return data
    if len(data) == 1:
        return data * total
    if len(data) > total:
        return data[:total]
    return data + [data[-1]] * (total - len(data))


def build_triton_v2_payload(
    triton_schema: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Build a Triton V2 probe from ``schema.response.triton`` metadata."""
    if not triton_schema or not isinstance(triton_schema, dict):
        return None
    input_defs = triton_schema.get("inputs")
    if not input_defs or not isinstance(input_defs, list):
        return None

    inputs = []
    for inp in input_defs:
        name = inp.get("name", "")
        datatype = inp.get("datatype", "BYTES")
        shape = _parse_shape(inp.get("shape", "[1]"))
        total = 1
        for dim in shape:
            total *= max(dim, 1)
        if "data" in inp and inp.get("data") is not None:
            data = _coerce_explicit_data(inp.get("data"), total)
        else:
            data = _dummy_data_for_input(name, datatype, shape)
        inputs.append(
            {"name": name, "datatype": datatype, "shape": shape, "data": data}
        )

    payload: Dict[str, Any] = {"inputs": inputs}
    output_defs = triton_schema.get("outputs")
    if output_defs and isinstance(output_defs, list):
        payload["outputs"] = [{"name": o.get("name")} for o in output_defs]
    return payload


# ── ULCA ──


_ULCA_DUMMY_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "nmt": {
        "input": [{"source": "Hello, how are you?"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    },
    "tts": {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "en"}, "gender": "female"},
    },
    "asr": {"audio": [{"audioContent": ""}], "config": {"language": {"sourceLanguage": "en"}}},
    "llm": {"input": [{"source": "Hello"}], "config": {}},
    "transliteration": {
        "input": [{"source": "namaste"}],
        "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}},
    },
    "language-detection": {"input": [{"source": "Hello, how are you?"}], "config": {}},
    "ocr": {
        "image": [{"imageContent": ""}],
        "config": {"language": {"sourceLanguage": "en"}},
    },
    "ner": {
        "input": [{"source": "John went to New York."}],
        "config": {"language": {"sourceLanguage": "en"}},
    },
    "speaker-diarization": {"audio": [{"audioContent": ""}], "config": {}},
    "audio-lang-detection": {"audio": [{"audioContent": ""}], "config": {}},
    "language-diarization": {"audio": [{"audioContent": ""}], "config": {}},
}


def build_ulca_payload(
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a ULCA test payload, preferring *request_schema* when present."""
    if request_schema:
        payload: Dict[str, Any] = {}
        for key, value in request_schema.items():
            if isinstance(value, str):
                payload[key] = "test"
            elif isinstance(value, dict):
                payload[key] = value
            elif isinstance(value, list):
                payload[key] = value if value else ["test"]
            else:
                payload[key] = value
        if payload:
            return payload

    if task_type in _ULCA_DUMMY_PAYLOADS:
        return _ULCA_DUMMY_PAYLOADS[task_type]
    return {"input": [{"source": "test"}]}


def build_probe_payload(
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    triton_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Return ``(payload, kind)`` where *kind* is ``"triton_v2"`` or ``"ulca"``."""
    triton_payload = build_triton_v2_payload(triton_schema)
    if triton_payload:
        return triton_payload, "triton_v2"
    return build_ulca_payload(task_type, request_schema), "ulca"

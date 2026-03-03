import os
from typing import List, Dict, Any


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def is_static_fallback_enabled() -> bool:
    """
    Global switch for all static fallbacks.
    Controlled via ENABLE_STATIC_FALLBACK env var.
    """
    return _env_flag("ENABLE_STATIC_FALLBACK", "false")


# ---------- NMT ----------

def get_nmt_static_response(input_texts: List[str]) -> Dict[str, Any]:
    """
    Return a minimal static NMT response matching the shape expected by routers.
    """
    return {
        "output": [
            {"source": text, "target": text}
            for text in input_texts
        ]
    }


# ---------- ASR ----------

def get_asr_static_response(num_inputs: int) -> Dict[str, Any]:
    """
    Return a minimal static ASR response with placeholder transcripts.
    """
    return {
        "output": [
            {
                "source": "",
                "target": "ASR service is temporarily unavailable. This is a static fallback response.",
            }
            for _ in range(num_inputs)
        ]
    }


# ---------- TTS ----------

def get_tts_static_response(num_outputs: int) -> Dict[str, Any]:
    """
    Return a minimal static TTS response with empty audio payloads.
    """
    # Empty / silent audio placeholder; services typically base64‑decode audioContent
    return {
        "audio": [
            {
                "audioContent": "",
                "format": "wav",
            }
            for _ in range(num_outputs)
        ]
    }


# ---------- LLM ----------

def get_llm_static_response_batch(input_texts: List[str]) -> Dict[str, Any]:
    """
    Return a minimal static LLM response batch.
    """
    return {
        "output": [
            {
                "source": text,
                "target": "LLM service is temporarily unavailable. This is a static fallback response.",
            }
            for text in input_texts
        ]
    }


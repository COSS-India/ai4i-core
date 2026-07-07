"""One-shot ASR latency measurement — stub mode (no live Triton needed).

Measures wall-clock time for each pipeline phase on a real audio file.
The Triton call is intercepted by the stub dispatcher and returns instantly,
so every millisecond shown is pure Python/orchestrator cost.

Run from this directory:
    python test_asr_latency.py
"""

import asyncio
import base64
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

# ── Mock pydub before anything in services/ loads it ─────────────────────────
pydub_mock = types.ModuleType("pydub")
pydub_mock.AudioSegment = MagicMock()
sys.modules["pydub"] = pydub_mock

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

AUDIO_FILE = Path(__file__).parent.parent.parent / "hindi_4s 1.wav"


async def run():
    from services.asr_service import ASRTaskService
    from trace.phase_timer import start_root_phases, collect_phases

    adapter_config = {
        "version": "1",
        "inputs": [
            {
                "tensor": "AUDIO_SAMPLES",
                "dtype": "FP32",
                "shape": [1, -1],
                "value_path": "audio.samples",
            },
        ],
        "outputs": [
            {
                "tensor": "TRANSCRIPTS",
                "dtype": "BYTES",
                "maps_to": "transcript",
                "response_key": "output[].source",
            }
        ],
        "response": {
            "static_item_fields": {"nBestTokens": None},
        },
    }

    service_info = {
        "name": "ASRTaskService",
        "endpoint": "http://triton-stub:8000/v2/models/whisper/infer",
        "api_key": None,
        "adapter_config": adapter_config,
    }

    svc = ASRTaskService(service_info=service_info)

    audio_bytes = AUDIO_FILE.read_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    payload = {
        "audio": [{"audioContent": audio_b64}],
        "config": {"language": {"sourceLanguage": "hi"}},
    }

    print(f"\nAudio file   : {AUDIO_FILE.name}")
    print(f"Duration     : ~4.4 s  (16 kHz mono, no resample needed)")
    print(f"File size    : {len(audio_bytes) / 1024:.1f} KB")
    print(f"Base64 size  : {len(audio_b64) / 1024:.1f} KB")
    print()

    # ── Run ───────────────────────────────────────────────────────────────────
    start_root_phases()                      # arm the phase-timer accumulator
    t_wall_start = time.perf_counter()
    result = await svc.process(payload, service_info)
    t_wall_ms = (time.perf_counter() - t_wall_start) * 1000

    phases = collect_phases()

    # ── Report ────────────────────────────────────────────────────────────────
    ordered = [
        "validate_ms",
        "preprocess_ms",
        "run_inference_ms",
        "build_payload_ms",
        "triton_ms",
        "output_convert_ms",
        "postprocess_ms",
    ]

    print(f"{'Phase':<26}  {'ms':>8}")
    print("-" * 38)
    accounted = 0.0
    for key in ordered:
        if key in phases:
            ms = phases[key]
            accounted += ms
            print(f"  {key:<24}  {ms:>8.1f}")

    # any extra keys the timer accumulated
    extras = {k: v for k, v in phases.items() if k not in ordered}
    for k, v in extras.items():
        if isinstance(v, (int, float)):
            print(f"  {k:<24}  {v:>8.1f}")
            accounted += v

    print("-" * 38)
    print(f"  {'TOTAL (wall clock)':<24}  {t_wall_ms:>8.1f}")
    print()

    output = result.get("output", [])
    if output:
        sys.stdout.buffer.write(b"Stub transcript : (Hindi text from stub response)\n\n")
    else:
        print()


if __name__ == "__main__":
    asyncio.run(run())

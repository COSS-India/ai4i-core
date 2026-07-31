"""Stub responses for the OpenAI-compatible /audio/* passthrough routes.

Unlike the Triton fixtures these are not KServe v2 shapes, and unlike
llm_responses.py they are not chat completions. The audio routes are a
verbatim passthrough of OpenAI's speech-to-text contract, and
_proxy_audio_upload decides the response type from the body it gets back:
a dict becomes JSONResponse, a str becomes PlainTextResponse. So the stub
has to honour ``response_format`` or the route returns the wrong content
type.

Five formats are served, matching what the route advertises:
    json          -> {"text": ...}
    verbose_json  -> {"task", "language", "duration", "text", "segments"}
    text          -> bare transcript string
    srt           -> SubRip cue block
    vtt           -> WebVTT cue block

Size thresholds are byte lengths of the uploaded file, not character counts.
The text thresholds in base_response_test.py (200 / 1000 chars) are useless
here: even one second of 16 kHz 16-bit mono audio is ~32 KB, so every real
upload would classify as LARGE. These are scaled for audio payloads.
"""

from typing import Any, Dict, Union

# Uploaded-file byte-length buckets.
SMALL_AUDIO_BYTES = 100_000     # < ~3 s of 16 kHz 16-bit mono
MEDIUM_AUDIO_BYTES = 1_000_000  # < ~30 s

_SMALL_TEXT = "Hello, how are you today?"
_MEDIUM_TEXT = (
    "Good morning everyone, and thank you for joining this call. "
    "We will walk through the quarterly numbers first, then move on to the "
    "roadmap for the next release and finish with an open question and "
    "answer session."
)
_LARGE_TEXT = (
    "Good morning everyone, and thank you for joining this call. "
    "We will walk through the quarterly numbers first, then move on to the "
    "roadmap for the next release and finish with an open question and "
    "answer session. Starting with revenue, we closed the quarter slightly "
    "ahead of plan, driven mainly by renewals in the enterprise segment. "
    "Support volumes were flat month over month, which is encouraging given "
    "the growth in active users. On the engineering side, the migration work "
    "completed on schedule and we have started decommissioning the legacy "
    "cluster. The remaining risks are concentrated in the data pipeline, "
    "where we are still waiting on an upstream dependency to be upgraded."
)


def _restore_terminator(sentence: str) -> str:
    """Splitting on '. ' strips the full stop; put it back without doubling up
    on a sentence that already ends in '?' or '!'."""
    return sentence if sentence.endswith((".", "?", "!")) else f"{sentence}."


def _segments(text: str, duration: float):
    """One segment per sentence, timings spread evenly across the duration."""
    sentences = [s.strip() for s in text.split(". ") if s.strip()]
    step = duration / max(len(sentences), 1)
    return [
        {
            "id": i,
            "seek": 0,
            "start": round(i * step, 2),
            "end": round((i + 1) * step, 2),
            "text": f" {_restore_terminator(s)}",
            "tokens": [],
            "temperature": 0.0,
            "avg_logprob": -0.25,
            "compression_ratio": 1.4,
            "no_speech_prob": 0.01,
        }
        for i, s in enumerate(sentences)
    ]


def _timestamp(seconds: float, sep: str) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    whole = int(secs)
    millis = int(round((secs - whole) * 1000))
    return f"{int(hours):02d}:{int(minutes):02d}:{whole:02d}{sep}{millis:03d}"


def _srt(text: str, duration: float) -> str:
    blocks = []
    for seg in _segments(text, duration):
        blocks.append(
            f"{seg['id'] + 1}\n"
            f"{_timestamp(seg['start'], ',')} --> {_timestamp(seg['end'], ',')}\n"
            f"{seg['text'].strip()}\n"
        )
    return "\n".join(blocks)


def _vtt(text: str, duration: float) -> str:
    blocks = ["WEBVTT\n"]
    for seg in _segments(text, duration):
        blocks.append(
            f"{_timestamp(seg['start'], '.')} --> {_timestamp(seg['end'], '.')}\n"
            f"{seg['text'].strip()}\n"
        )
    return "\n".join(blocks)


def _bundle(text: str, duration: float) -> Dict[str, Union[Dict[str, Any], str]]:
    """Every supported response_format for one size bucket."""
    return {
        "json": {"text": text},
        "verbose_json": {
            "task": "transcribe",
            "language": "english",
            "duration": duration,
            "text": text,
            "segments": _segments(text, duration),
        },
        "text": text,
        "srt": _srt(text, duration),
        "vtt": _vtt(text, duration),
    }


SMALL_TRANSCRIPTION_RESPONSES = _bundle(_SMALL_TEXT, 2.5)
MEDIUM_TRANSCRIPTION_RESPONSES = _bundle(_MEDIUM_TEXT, 14.0)
LARGE_TRANSCRIPTION_RESPONSES = _bundle(_LARGE_TEXT, 48.0)

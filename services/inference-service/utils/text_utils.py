"""Stateless text helpers shared across text-backed task services.

Pure functions, no task state. Text services compose these instead of
re-implementing sanitisation, normalisation, and chunking.
"""

from __future__ import annotations


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


def chunk_text(text: str, max_length: int) -> list[str]:
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

    chunks: list[str] = []
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

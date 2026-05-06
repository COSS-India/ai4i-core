"""Shared StandardSpanManager singleton for the llm-service."""

from ai4icore_telemetry import StandardSpanManager

llm_spans = StandardSpanManager("llm")

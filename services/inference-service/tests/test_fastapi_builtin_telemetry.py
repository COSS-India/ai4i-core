"""
FastAPI 0.142+ adds its own OpenTelemetry spans, metrics and logs whenever a
tracer provider is set. create_inference_app() sets one in setup_tracing() and
turns FastAPI's built-in telemetry off, so the service's spans are not nested
under FastAPI's HTTP spans. FastAPI accepts unknown telemetry keys silently,
so a misspelt key or a rename in a later FastAPI release would turn it back on
with nothing else failing.
"""

import sys

from fastapi import FastAPI

sys.path.insert(0, ".")

from app_factory import create_inference_app


def test_fastapi_builtin_telemetry_disabled():
    app = create_inference_app()

    # Control: setup_tracing() has set a tracer provider, so a FastAPI app
    # without the opt-out reports its built-in telemetry enabled.
    assert FastAPI()._native_telemetry.enabled()
    assert not app._native_telemetry.enabled()

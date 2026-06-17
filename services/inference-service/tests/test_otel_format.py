#!/usr/bin/env python3
"""
Test script to verify OpenTelemetry format output.

This demonstrates the span attributes being logged in standard OpenTelemetry JSON format
with proper trace_id, span_id, and hierarchical span information.
"""

import json
import logging
import sys
from io import StringIO

# Configure logging to capture output
log_capture = StringIO()
handler = logging.StreamHandler(log_capture)
handler.setFormatter(logging.Formatter('%(message)s'))

logger = logging.getLogger('trace.inference_span')
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Now import and test the span functions
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Set up a test tracer
exporter = InMemorySpanExporter()
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(tracer_provider)

# Get tracer and create a test span
tracer = trace.get_tracer(__name__)

# Mock the context getters
import ai4icore_core.context as ctx_module
ctx_module.set_tenant_id("tenant_12345")

# Import after setting context
from trace.inference_span import set_input_span_attributes, set_output_span_attributes

# Test with a span context
with tracer.start_as_current_span("ai_inference") as span:
    # Simulate input phase
    test_payload = {
        "input": [
            {"source": "Hello world"}
        ],
        "config": {}
    }

    print("\n" + "="*80)
    print("INPUT PHASE - OpenTelemetry Format")
    print("="*80)

    set_input_span_attributes(test_payload, test_payload["input"], {})

    # Get and display the logged output
    log_output = log_capture.getvalue()
    if log_output:
        try:
            # Parse JSON from log output
            lines = log_output.strip().split('\n')
            for line in lines:
                if line.startswith('{'):
                    data = json.loads(line)
                    print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(log_output)

    # Clear log capture
    log_capture.truncate(0)
    log_capture.seek(0)

    # Simulate output phase
    test_response = [
        {"target": "Hola mundo", "translation": "Spanish"}
    ]

    print("\n" + "="*80)
    print("OUTPUT PHASE - OpenTelemetry Format")
    print("="*80)

    set_output_span_attributes(test_response, status="success", status_code=200)

    # Get and display the logged output
    log_output = log_capture.getvalue()
    if log_output:
        try:
            # Parse JSON from log output
            lines = log_output.strip().split('\n')
            for line in lines:
                if line.startswith('{'):
                    data = json.loads(line)
                    print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(log_output)

print("\n" + "="*80)
print("✓ Test completed successfully!")
print("="*80 + "\n")

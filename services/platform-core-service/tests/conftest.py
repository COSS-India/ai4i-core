"""
Shared pytest configuration for platform-core-service unit tests.

CoreSettings is instantiated at module import time (config.py:173), so env vars
must be set here at module level — before pytest imports any test module. An
autouse fixture would run too late (after imports) and cause a ValidationError
during collection.
"""

import os

os.environ.setdefault("SERVICE_NAME", "platform-core-service")
os.environ.setdefault("SERVICE_VERSION", "0.0.0-test")
os.environ.setdefault("API_VERSION", "v1")
os.environ.setdefault("NER_SERVICE_URL", "http://localhost:9001")
os.environ.setdefault("PII_LLM_URL", "http://localhost:9002")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

"""Test-time environment defaults for the unit suite.

Set at module scope, not in a fixture: pytest imports every test module before
any fixture runs, and a consumer's config module may instantiate its settings
during import.

Every value is deliberately unreachable.  That is the safety property, not an
inconvenience — no test may touch a live broker, database or Redis, and a code
path that tries must fail loudly rather than quietly succeed against whatever
happens to be running on the developer's machine.
"""
import os
import sys

import pytest

# tests/conftest.py -> tests -> service root.  Two levels, not one: this file
# moved from the service root into tests/.  The service root is
# what has to be importable, so `import bootstrap` and `import consumers.<n>.main`
# resolve.
_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

os.environ.setdefault("KAFKA_SERVER", "localhost:1")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("PLATFORM_CORE_DB", "ai4iplatform_core_test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("TOPIC_PAY_PER_USE", "kafka-topic-otel-trace")
os.environ.setdefault("AUTH_SERVICE_URL", "http://auth.invalid")


@pytest.fixture(autouse=True)
def _clear_settings_caches():
    """Settings accessors are @lru_cache(maxsize=1) and nothing clears them.

    Without this every monkeypatch.setenv test is order-coupled: whichever test
    reads a settings object first wins for the whole session, and the second one
    passes or fails depending on collection order.  Cleared on the way in AND on
    the way out, so a test that populates the cache cannot leak into the next.
    """
    from bootstrap import config as bootstrap_config

    accessors = (
        bootstrap_config.get_kafka_settings,
        bootstrap_config.get_db_settings,
        bootstrap_config.get_redis_settings,
    )
    for accessor in accessors:
        accessor.cache_clear()
    yield
    for accessor in accessors:
        accessor.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _ignore_deployment_env_file(tmp_path_factory):
    """Run the suite from a directory holding no .env.

    Every settings class declares ``env_file = ".env"``, which pydantic resolves
    against the CURRENT WORKING DIRECTORY — the service root, where a real
    deployment .env sits.  Left alone, `pytest` asserts against whatever the
    developer happens to have configured locally: a stale
    ``KAFKA_AUTO_OFFSET_RESET=earliest`` line quietly turns the default test
    green-or-red depending on the machine, and CI (no .env) disagrees with the
    laptop.  The values tests do need come from the environment above.

    Every path used by the tests is absolute, so the chdir affects nothing else.

    This is a fixture, so it runs after collection: a settings object built at
    a test module's TOP LEVEL is constructed before it fires and must pass
    ``_env_file=None`` itself.
    """
    original = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("no-dotenv"))
    try:
        yield
    finally:
        os.chdir(original)

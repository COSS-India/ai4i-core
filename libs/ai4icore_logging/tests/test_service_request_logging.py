"""
Unit tests for ServiceRequestLoggingMiddleware — log-level mapping and 4xx logging.

Covers:
  1. 4xx status codes map to WARNING level (not ERROR).
  2. 4xx logs pass through when WARNING is in ALLOWED_LOG_LEVELS.
  3. 4xx logs are blocked when WARNING is excluded from ALLOWED_LOG_LEVELS (old config).
  4. Middleware emits exactly ONE log per 4xx request (no double-log from exception handlers).
  5. 5xx still logs as ERROR, 2xx still logs as INFO.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ai4icore_logging.service_request_logging import ServiceRequestLoggingMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_DEFAULTS = dict(
    exclude_health_logs=False,
    exclude_metrics_logs=False,
    exclude_options_logs=True,
    request_log_include_paths="",
    min_log_level="INFO",
    use_kafka_logging=False,
    service_name="test-service",
)


def _make_middleware(*, include_4xx: bool, allowed_log_levels: str) -> ServiceRequestLoggingMiddleware:
    """Build middleware with controlled env, bypassing real app_env reads."""
    with patch("ai4icore_logging.service_request_logging.app_env") as env:
        for k, v in _ENV_DEFAULTS.items():
            setattr(env, k, v)
        env.allowed_log_levels = allowed_log_levels
        mw = ServiceRequestLoggingMiddleware(MagicMock(), include_4xx=include_4xx)
    return mw


def _make_mock_request(method: str = "POST", path: str = "/api/v1/nmt/inference") -> MagicMock:
    req = MagicMock()
    req.method = method
    req.url.path = path
    return req


def _make_mock_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    return resp


# ---------------------------------------------------------------------------
# 1. _should_log_by_level — 4xx maps to WARNING
# ---------------------------------------------------------------------------

class TestShouldLogByLevel:

    def test_4xx_passes_when_warning_in_allowed_levels(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")
        assert mw._should_log_by_level(400) is True
        assert mw._should_log_by_level(401) is True
        assert mw._should_log_by_level(422) is True

    def test_4xx_blocked_when_warning_not_in_allowed_levels(self):
        # Old config had INFO,ERROR — WARNING excluded → 4xx must be silently dropped
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,ERROR")
        assert mw._should_log_by_level(422) is False
        assert mw._should_log_by_level(400) is False

    def test_5xx_passes_as_error(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")
        assert mw._should_log_by_level(500) is True
        assert mw._should_log_by_level(503) is True

    def test_2xx_passes_as_info(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")
        assert mw._should_log_by_level(200) is True


# ---------------------------------------------------------------------------
# 2. dispatch — correct log level emitted per status code
# ---------------------------------------------------------------------------

class TestDispatchLogLevel:

    def test_4xx_logged_as_warning_not_error(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")

        async def _run():
            with patch.object(mw, "logger") as mock_logger, \
                 patch.object(mw, "_base_context", return_value={}):
                await mw.dispatch(
                    _make_mock_request(),
                    AsyncMock(return_value=_make_mock_response(422)),
                )
                mock_logger.warning.assert_called_once()
                mock_logger.error.assert_not_called()
                mock_logger.info.assert_not_called()

        asyncio.run(_run())

    def test_5xx_logged_as_error_not_warning(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")

        async def _run():
            with patch.object(mw, "logger") as mock_logger, \
                 patch.object(mw, "_base_context", return_value={}):
                await mw.dispatch(
                    _make_mock_request(),
                    AsyncMock(return_value=_make_mock_response(503)),
                )
                mock_logger.error.assert_called_once()
                mock_logger.warning.assert_not_called()

        asyncio.run(_run())

    def test_2xx_logged_as_info(self):
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")

        async def _run():
            with patch.object(mw, "logger") as mock_logger, \
                 patch.object(mw, "_base_context", return_value={}):
                await mw.dispatch(
                    _make_mock_request(),
                    AsyncMock(return_value=_make_mock_response(200)),
                )
                mock_logger.info.assert_called_once()
                mock_logger.warning.assert_not_called()
                mock_logger.error.assert_not_called()

        asyncio.run(_run())

    def test_4xx_silent_when_include_4xx_false(self):
        mw = _make_middleware(include_4xx=False, allowed_log_levels="INFO,WARNING,ERROR")

        async def _run():
            with patch.object(mw, "logger") as mock_logger:
                await mw.dispatch(
                    _make_mock_request(),
                    AsyncMock(return_value=_make_mock_response(422)),
                )
                mock_logger.warning.assert_not_called()
                mock_logger.error.assert_not_called()

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. No double-log — middleware emits exactly one log per 4xx request
# ---------------------------------------------------------------------------

class TestNoDoubleLog:

    def test_exactly_one_log_per_4xx_request(self):
        """
        Middleware is the sole logger for 4xx. Exception handlers have no
        logger calls. This verifies exactly one WARNING is emitted per 422.
        """
        mw = _make_middleware(include_4xx=True, allowed_log_levels="INFO,WARNING,ERROR")
        call_log: list = []

        async def _run():
            with patch.object(mw, "logger") as mock_logger, \
                 patch.object(mw, "_base_context", return_value={}):
                mock_logger.warning.side_effect = lambda *a, **kw: call_log.append("warning")
                mock_logger.error.side_effect = lambda *a, **kw: call_log.append("error")
                mock_logger.info.side_effect = lambda *a, **kw: call_log.append("info")
                await mw.dispatch(
                    _make_mock_request(),
                    AsyncMock(return_value=_make_mock_response(422)),
                )

        asyncio.run(_run())

        assert len(call_log) == 1, f"Expected 1 log, got {len(call_log)}: {call_log}"
        assert call_log[0] == "warning"

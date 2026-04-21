"""
Unit tests verifying exception handlers do NOT emit logger calls directly.

The middleware (ServiceRequestLoggingMiddleware) is the sole place that logs
4xx/5xx requests. If handlers also call logger, each error produces two log
entries in OpenSearch. These tests enforce that contract.
"""
import inspect

from ai4icore_exceptions.handlers import register_exception_handlers


def _source_block(handler_name: str, next_handler_name: str) -> str:
    """Extract source code of one handler function from register_exception_handlers."""
    src = inspect.getsource(register_exception_handlers)
    start = src.find(f"async def {handler_name}")
    end = src.find(f"async def {next_handler_name}")
    assert start != -1, f"Handler '{handler_name}' not found in source"
    return src[start:end] if end != -1 else src[start:]


class TestHandlersHaveNoDirectLoggerCalls:

    def test_validation_app_error_has_no_logger_call(self):
        """
        validation_app_error (custom ValidationError, 422) must not call
        logger directly — middleware logs it once via dispatch.
        """
        block = _source_block("validation_app_error", "service_error_handler")
        assert "logger.error" not in block, "validation_app_error must not call logger.error"
        assert "logger.warning" not in block, "validation_app_error must not call logger.warning"

    def test_request_validation_handler_has_no_logger_call(self):
        """
        request_validation_error_handler (Pydantic 422) must not call
        logger directly — middleware logs it once via dispatch.
        """
        block = _source_block("request_validation_error_handler", "http_exception_handler")
        assert "logger.error" not in block, "request_validation_error_handler must not call logger.error"
        assert "logger.warning" not in block, "request_validation_error_handler must not call logger.warning"

"""
Endpoint validation must leave a trace in the pod logs when it fails.

Before this, a failed service creation was completely silent: the pre-probe
rejections (URL format, SSRF, the LLM path check, pollingUrl) return before
validate_endpoint reaches its own log line, RequestMiddleware drops the
resulting 400, and neither exception handler logs. The user saw an error
toast and the cluster recorded nothing.

_validate_endpoint_for_model is the single place every failure passes
through, so these tests drive it directly and assert on caplog.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import importlib

# Deliberately no sys.modules stubs here. Sibling test modules install
# ModuleType placeholders for app.models / app.repositories at import time,
# which makes those packages unimportable for every test module collected
# afterwards. The real modules import fine, so this file uses them.

# model-management directory is hyphenated; plain imports cannot resolve it.
_service_service_module = importlib.import_module(
    "app.services.model-management.service_service"
)
ServiceService = _service_service_module.ServiceService
EndpointValidationFailedError = _service_service_module.EndpointValidationFailedError
PublishedServiceImmutableError = _service_service_module.PublishedServiceImmutableError

from app.core.exceptions import EntityNotFoundError

from app.utils.endpoint_validator import (
    EndpointValidationResult,
    ValidationDetail,
    ValidationLevel,
    ValidationStatus,
)


ENDPOINT = "http://10.185.33.143:31053"
# A sentinel, not a credential. Every test below asserts it never reaches a
# log record, so it has to be distinctive enough to grep for.
NEVER_LOG_VALUE = "sentinel-value-that-must-not-be-logged"


def _make_svc() -> ServiceService:
    return ServiceService(
        service_repo=MagicMock(),
        model_repo=MagicMock(),
        cache=MagicMock(),
    )


def _result(*messages: str) -> EndpointValidationResult:
    """A failed validation carrying *messages* as its FAILED details."""
    return EndpointValidationResult(
        is_valid=False,
        endpoint=ENDPOINT,
        details=[
            ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=message,
            )
            for message in messages
        ],
    )


def _passing_result() -> EndpointValidationResult:
    return EndpointValidationResult(
        is_valid=True,
        endpoint=ENDPOINT,
        details=[
            ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.PASSED,
                message="URL format is valid.",
            )
        ],
    )


@pytest.fixture
def patched_validate(monkeypatch):
    """Replace validate_endpoint; return a setter for what it should yield."""

    def _set(result: EndpointValidationResult) -> AsyncMock:
        mock = AsyncMock(return_value=result)
        monkeypatch.setattr(_service_service_module, "validate_endpoint", mock)
        return mock

    return _set


async def _run(svc: ServiceService, *, api_key=None, task_type="llm") -> None:
    await svc._validate_endpoint_for_model(
        endpoint=ENDPOINT,
        api_key=api_key,
        model_inference_endpoint={},
        task_type=task_type,
        expected_response_schema=None,
    )


def _warnings(caplog) -> list:
    return [r for r in caplog.records if r.levelname == "WARNING"]


# The failure paths from AI4IDS-2768, each previously silent.
SILENT_FAILURES = [
    pytest.param(
        "Endpoint host is not allowed for probing (SSRF protection). "
        "Blocked hostname: '10.185.33.143'",
        id="ssrf",
    ),
    pytest.param(
        "URL missing scheme (http/https). Got: '10.185.33.143:31053'",
        id="url-format",
    ),
    pytest.param(
        "For LLM services, endpoint must be host:port only, with no path",
        id="llm-extra-path",
    ),
    pytest.param(
        "Polling endpoint host is not allowed for probing (SSRF protection). "
        "Blocked hostname: '169.254.169.254'",
        id="polling-url",
    ),
    pytest.param(
        "Could not connect to endpoint: http://10.185.33.143:31053",
        id="probe-transport",
    ),
    pytest.param(
        "Response did not match the expected schema - response.choices: "
        "missing from response.",
        id="response-shape",
    ),
]


class TestFailuresAreLogged:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message", SILENT_FAILURES)
    async def test_failure_emits_a_warning(self, message, caplog, patched_validate):
        patched_validate(_result(message))
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _run(svc)

        warnings = _warnings(caplog)
        assert warnings, "no WARNING logged for a failed validation"
        logged = warnings[0].getMessage()
        assert message in logged
        assert ENDPOINT in logged

    @pytest.mark.asyncio
    async def test_every_failure_reason_is_logged_not_just_the_first(
        self, caplog, patched_validate
    ):
        patched_validate(_result("first reason", "second reason"))
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _run(svc)

        logged = _warnings(caplog)[0].getMessage()
        assert "first reason" in logged
        assert "second reason" in logged

    @pytest.mark.asyncio
    async def test_task_type_is_logged(self, caplog, patched_validate):
        patched_validate(_result("boom"))
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _run(svc, task_type="asr")

        assert "asr" in _warnings(caplog)[0].getMessage()


class TestOneLinePerFailure:
    @pytest.mark.asyncio
    async def test_failure_produces_exactly_one_record(
        self, caplog, patched_validate
    ):
        """A failure is one readable line, not an INFO plus a WARNING."""
        patched_validate(_result("Could not connect to endpoint: " + ENDPOINT))
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _run(svc)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"

    @pytest.mark.asyncio
    async def test_success_logs_no_warning(self, caplog, patched_validate):
        patched_validate(_passing_result())
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            await _run(svc)

        assert not _warnings(caplog)


class TestOtherRejectionsAreLogged:
    """Endpoint validation was not the only silent 4xx. Model-not-found,
    duplicate name, duplicate serviceId, not-found and published-immutable
    were all equally invisible, for the same two reasons."""

    @pytest.mark.asyncio
    async def test_delete_of_missing_service_logs_a_warning(self, caplog):
        svc = _make_svc()
        svc._services.get_by_service_id = AsyncMock(return_value=None)

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EntityNotFoundError):
                await svc.delete_service("no-such-service")

        warnings = _warnings(caplog)
        assert warnings
        assert "no-such-service" in warnings[0].getMessage()

    @pytest.mark.asyncio
    async def test_delete_of_published_service_logs_the_code(self, caplog):
        svc = _make_svc()
        published = MagicMock()
        published.is_published = True
        published.service_id = "svc-1"
        svc._services.get_by_service_id = AsyncMock(return_value=published)

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(PublishedServiceImmutableError):
                await svc.delete_service("svc-1")

        assert "PUBLISHED_SERVICE_IMMUTABLE" in _warnings(caplog)[0].getMessage()

    @pytest.mark.asyncio
    async def test_successful_delete_logs_no_warning(self, caplog):
        svc = _make_svc()
        instance = MagicMock()
        instance.is_published = False
        instance.service_id = "svc-1"
        svc._services = AsyncMock()
        svc._services.get_by_service_id = AsyncMock(return_value=instance)

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            await svc.delete_service("svc-1")

        assert not _warnings(caplog)

    @pytest.mark.parametrize(
        "method_name",
        ["create_service", "update_service", "update_service_endpoints", "delete_service"],
    )
    def test_every_write_entry_point_is_covered(self, method_name):
        """Guards the decorator against being dropped from a method during a
        later refactor, which would silently restore the blind spot."""
        method = getattr(ServiceService, method_name)
        assert hasattr(method, "__wrapped__"), f"{method_name} is not decorated"

    @pytest.mark.asyncio
    async def test_endpoint_validation_failure_is_not_logged_twice(self, caplog):
        """The decorator defers to _validate_endpoint_for_model, which logs
        the same failure with the endpoint and task type."""

        @_service_service_module._log_rejections
        async def _raises():
            raise EndpointValidationFailedError(
                message="Service endpoint validation failed.", errors=["blocked"]
            )

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _raises()

        assert not caplog.records


class TestSecretsAreNotLogged:
    @pytest.mark.asyncio
    async def test_api_key_never_appears_in_any_record(self, caplog, patched_validate):
        """The api_key is passed straight into validation, so it is one
        careless format string away from the pod logs."""
        patched_validate(_result("Endpoint host is not allowed for probing."))
        svc = _make_svc()

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await _run(svc, api_key=NEVER_LOG_VALUE)

        for record in caplog.records:
            assert NEVER_LOG_VALUE not in record.getMessage()

    @pytest.mark.asyncio
    async def test_embedded_credentials_are_stripped_from_the_url(
        self, caplog, patched_validate, monkeypatch
    ):
        patched_validate(_result("blocked"))
        svc = _make_svc()
        # Assembled rather than written as a literal, so this stays a test
        # fixture and not something a secret scanner has to reason about.
        userinfo = "admin:" + NEVER_LOG_VALUE
        credentialed = f"http://{userinfo}@10.185.33.143:31053"

        with caplog.at_level("INFO", logger=_service_service_module.__name__):
            with pytest.raises(EndpointValidationFailedError):
                await svc._validate_endpoint_for_model(
                    endpoint=credentialed,
                    api_key=None,
                    model_inference_endpoint={},
                    task_type="llm",
                    expected_response_schema=None,
                )

        for record in caplog.records:
            assert NEVER_LOG_VALUE not in record.getMessage()

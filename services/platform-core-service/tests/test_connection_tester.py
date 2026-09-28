"""Unit tests for app/utils/connection_tester.py (service-creation "Try it").

Covers the success path and that each failure is attributed to the right
culprit: MODEL_JSON, ENDPOINT, PAYLOAD, AUTH or RESPONSE_FORMAT.
"""

import httpx
import pytest

from app.utils import connection_tester as ct
from app.utils import endpoint_validator as ev
from app.utils.connection_tester import CheckStatus, FailureCategory, run_connection_test


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text or ("" if json_body is None else str(json_body))

    def json(self):
        if self._json_body is None:
            raise ValueError("not json")
        return self._json_body


class _FakeAsyncClient:
    def __init__(self, responses=None, exc=None):
        self._responses = list(responses or [])
        self._exc = exc
        self.calls = []  # (url, json, headers)
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        if self._exc:
            raise self._exc
        return self._responses.pop(0)


async def _async_true(_hostname, **_kw):
    return True


async def _async_false(_hostname, **_kw):
    return False


@pytest.fixture
def safe_hosts(monkeypatch):
    monkeypatch.setattr(ev, "is_safe_host", _async_true)


def _install(monkeypatch, client):
    monkeypatch.setattr(ct.httpx, "AsyncClient", client)
    return client


NMT_PARAMS = {
    "request_schema": {"input": [{"source": "hi"}], "config": {"language": {"sourceLanguage": "en"}}},
    "triton_schema": None,
    "is_sync_api": True,
    "polling_url": None,
    "poll_interval_ms": None,
    "model_name": None,
}
NMT_OK = {"output": [{"source": "test", "target": "परीक्षण"}]}


@pytest.mark.asyncio
async def test_success_with_model_json_payload(monkeypatch, safe_hosts):
    client = _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, NMT_OK)]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.success is True
    assert out.failureCategory is None
    assert out.statusCode == 200
    assert out.responseBody == NMT_OK
    assert out.payloadSource == "model_json"
    assert client.kwargs["follow_redirects"] is False
    assert [c.status for c in out.checks] == [CheckStatus.PASSED] * 5


@pytest.mark.asyncio
async def test_custom_payload_sent_verbatim_with_bearer(monkeypatch, safe_hosts):
    client = _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, NMT_OK)]))
    out = await run_connection_test(
        endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS,
        custom_payload='{"input": [{"source": "Good morning"}]}', api_key="tok",
    )
    assert out.success is True
    assert out.payloadSource == "custom"
    _url, body, headers = client.calls[0]
    assert body == {"input": [{"source": "Good morning"}]}
    assert headers["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_invalid_json_payload_is_payload_failure_without_network(monkeypatch, safe_hosts):
    client = _install(monkeypatch, _FakeAsyncClient())
    out = await run_connection_test(
        endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS,
        custom_payload='{"input": [,]}',
    )
    assert out.success is False
    assert out.failureCategory == FailureCategory.PAYLOAD
    assert "line 1" in out.failureReason
    assert client.calls == []


@pytest.mark.asyncio
async def test_4xx_blames_custom_payload(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(422, {"detail": "config missing"})]))
    out = await run_connection_test(
        endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS,
        custom_payload={"input": []},
    )
    assert out.failureCategory == FailureCategory.PAYLOAD
    assert out.statusCode == 422
    assert out.responseBody == {"detail": "config missing"}


@pytest.mark.asyncio
async def test_4xx_blames_model_json_when_payload_came_from_it(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(400, {"detail": "bad"})]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.MODEL_JSON


@pytest.mark.asyncio
async def test_malformed_model_schema_fails_before_network(monkeypatch, safe_hosts):
    client = _install(monkeypatch, _FakeAsyncClient())
    params = {**NMT_PARAMS, "request_schema": ["not", "an", "object"]}
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=params)
    assert out.failureCategory == FailureCategory.MODEL_JSON
    assert "schema.request" in out.failureReason
    assert client.calls == []


@pytest.mark.asyncio
async def test_malformed_model_schema_only_warns_with_custom_payload(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, NMT_OK)]))
    params = {**NMT_PARAMS, "request_schema": "oops"}
    out = await run_connection_test(
        endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=params,
        custom_payload={"input": [{"source": "x"}]},
    )
    assert out.success is True
    assert out.checks[0].status == CheckStatus.WARNING


@pytest.mark.asyncio
async def test_missing_task_type_is_model_json_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient())
    out = await run_connection_test(endpoint="https://x.example.com", task_type=None, model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.MODEL_JSON


@pytest.mark.asyncio
async def test_ssrf_blocked_host_is_endpoint_failure(monkeypatch):
    monkeypatch.setattr(ev, "is_safe_host", _async_false)
    client = _install(monkeypatch, _FakeAsyncClient())
    out = await run_connection_test(endpoint="http://10.0.0.5/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert "SSRF" in out.failureReason
    assert client.calls == []


@pytest.mark.asyncio
async def test_bad_url_is_endpoint_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient())
    out = await run_connection_test(endpoint="nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT


@pytest.mark.asyncio
async def test_llm_endpoint_with_path_is_endpoint_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient())
    out = await run_connection_test(
        endpoint="https://llm.example.com/v1/chat/completions", task_type="llm",
        model_params={**NMT_PARAMS, "model_name": "m"},
    )
    assert out.failureCategory == FailureCategory.ENDPOINT


@pytest.mark.asyncio
async def test_llm_unknown_model_404_blames_model_json(monkeypatch, safe_hosts):
    client = _install(monkeypatch, _FakeAsyncClient([
        _FakeResponse(404, {"message": "The model `x` does not exist."}, text='{"message": "The model `x` does not exist."}')
    ]))
    out = await run_connection_test(
        endpoint="https://llm.example.com:8000", task_type="llm",
        model_params={**NMT_PARAMS, "request_schema": None, "model_name": "x"},
    )
    assert client.calls[0][0] == "https://llm.example.com:8000/v1/chat/completions"
    assert out.failureCategory == FailureCategory.MODEL_JSON


@pytest.mark.asyncio
async def test_plain_404_is_endpoint_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(404, None, text="Not Found")]))
    out = await run_connection_test(endpoint="https://nmt.example.com/wrong", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert out.responseBody == "Not Found"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure(monkeypatch, safe_hosts, status):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(status, {"detail": "no"})]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.AUTH


@pytest.mark.asyncio
async def test_5xx_is_endpoint_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(503, None, text="upstream down")]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert out.statusCode == 503


@pytest.mark.asyncio
async def test_redirect_not_followed(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(302, None)]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert "redirect" in out.failureReason.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_transport_errors_are_endpoint_failures(monkeypatch, safe_hosts, exc):
    _install(monkeypatch, _FakeAsyncClient(exc=exc))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert out.statusCode is None


@pytest.mark.asyncio
async def test_non_json_2xx_is_response_format_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, None, text="<html>")]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.RESPONSE_FORMAT


@pytest.mark.asyncio
async def test_shape_mismatch_is_response_format_failure(monkeypatch, safe_hosts):
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, {"result": "x"})]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.failureCategory == FailureCategory.RESPONSE_FORMAT
    assert out.responseBody == {"result": "x"}


@pytest.mark.asyncio
async def test_large_response_body_is_truncated(monkeypatch, safe_hosts):
    big = {"output": [{"target": "x" * (ct.MAX_ECHOED_BODY_CHARS + 10)}]}
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(200, big)]))
    out = await run_connection_test(endpoint="https://nmt.example.com/infer", task_type="nmt", model_params=NMT_PARAMS)
    assert out.success is True
    assert out.responseTruncated is True
    assert isinstance(out.responseBody, str)


@pytest.mark.asyncio
async def test_async_model_polls_until_done(monkeypatch, safe_hosts):
    monkeypatch.setattr(ct.asyncio, "sleep", _noop_sleep)
    client = _install(monkeypatch, _FakeAsyncClient([
        _FakeResponse(202, {"jobId": "1"}), _FakeResponse(202, {"jobId": "1"}), _FakeResponse(200, NMT_OK),
    ]))
    params = {**NMT_PARAMS, "is_sync_api": False, "polling_url": "https://nmt.example.com/poll"}
    out = await run_connection_test(endpoint="https://nmt.example.com/submit", task_type="nmt", model_params=params)
    assert out.success is True
    assert [c[0] for c in client.calls] == [
        "https://nmt.example.com/submit", "https://nmt.example.com/poll", "https://nmt.example.com/poll",
    ]
    assert client.calls[1][1] == {"jobId": "1"}


@pytest.mark.asyncio
async def test_async_model_poll_budget_exhausted(monkeypatch, safe_hosts):
    monkeypatch.setattr(ct.asyncio, "sleep", _noop_sleep)
    _install(monkeypatch, _FakeAsyncClient([_FakeResponse(202, {})] * 4))
    params = {**NMT_PARAMS, "is_sync_api": False, "polling_url": "https://nmt.example.com/poll"}
    out = await run_connection_test(
        endpoint="https://nmt.example.com/submit", task_type="nmt", model_params=params, max_poll_attempts=3,
    )
    assert out.failureCategory == FailureCategory.ENDPOINT
    assert "did not complete" in out.failureReason


async def _noop_sleep(_s):
    return None

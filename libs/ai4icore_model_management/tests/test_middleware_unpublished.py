"""
Tests for unpublished service check in Model Resolution Middleware.
Verifies that inference is rejected with 403 when service is unpublished.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai4icore_model_management.client import ModelManagementClient, ServiceInfo
from ai4icore_model_management.middleware import (
    ModelResolutionMiddleware,
    UnpublishedServiceError,
    SERVICE_UNPUBLISHED_CODE,
    SERVICE_UNPUBLISHED_MESSAGE,
)


@pytest.fixture
def mock_client():
    return MagicMock(spec=ModelManagementClient)


@pytest.fixture
def middleware(mock_client):
    app = MagicMock()
    return ModelResolutionMiddleware(
        app,
        model_management_client=mock_client,
        redis_client=None,
        cache_ttl_seconds=300,
        default_triton_endpoint=None,
        default_triton_api_key=None,
    )


@pytest.mark.asyncio
async def test_resolve_service_raises_when_service_unpublished(middleware, mock_client):
    """When get_service returns is_published=False, _resolve_service raises UnpublishedServiceError."""
    service_id = "test-service-id"
    unpublished_info = ServiceInfo(
        service_id=service_id,
        model_id="model-1",
        endpoint="http://example.com:8000",
        is_published=False,
    )
    middleware._get_service_info = AsyncMock(return_value=unpublished_info)

    with pytest.raises(UnpublishedServiceError) as exc_info:
        await middleware._resolve_service(service_id, {})

    assert exc_info.value.service_id == service_id
    middleware._get_service_info.assert_called_once_with(service_id, {})


@pytest.mark.asyncio
async def test_resolve_service_raises_when_is_published_none(middleware):
    """When is_published is None (e.g. old API), treat as unpublished."""
    service_id = "test-service-id"
    info_none = ServiceInfo(
        service_id=service_id,
        model_id="model-1",
        endpoint="http://example.com:8000",
        is_published=None,
    )
    middleware._get_service_info = AsyncMock(return_value=info_none)

    with pytest.raises(UnpublishedServiceError) as exc_info:
        await middleware._resolve_service(service_id, {})

    assert exc_info.value.service_id == service_id


@pytest.mark.asyncio
async def test_resolve_service_allows_when_service_published(middleware):
    """When is_published is True and registry returns entry, no UnpublishedServiceError."""
    service_id = "test-service-id"
    published_info = ServiceInfo(
        service_id=service_id,
        model_id="model-1",
        endpoint="http://example.com:8000",
        is_published=True,
    )
    middleware._get_service_info = AsyncMock(return_value=published_info)
    middleware._get_service_registry_entry = AsyncMock(
        return_value=("example.com:8000", "test-model")
    )

    endpoint, model_name, client = await middleware._resolve_service(service_id, {})

    assert endpoint == "example.com:8000"
    assert model_name == "test-model"
    assert client is not None


@pytest.mark.asyncio
async def test_resolve_service_allows_when_service_not_found(middleware):
    """When get_service returns None (service not found), no UnpublishedServiceError - resolution fails later."""
    service_id = "missing-service"
    middleware._get_service_info = AsyncMock(return_value=None)
    middleware._get_service_registry_entry = AsyncMock(return_value=None)

    endpoint, model_name, client = await middleware._resolve_service(service_id, {})

    assert endpoint is None
    assert model_name is None
    assert client is None


def test_unpublished_error_code_and_message():
    """Verify error code and message are set for API responses."""
    assert SERVICE_UNPUBLISHED_CODE == "SERVICE_UNPUBLISHED"
    assert "unpublished" in SERVICE_UNPUBLISHED_MESSAGE.lower()
    assert len(SERVICE_UNPUBLISHED_MESSAGE) > 0

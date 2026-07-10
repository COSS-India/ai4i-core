from typing import Any, Callable, Dict, Optional

import httpx

from ai4i_core.logging import get_logger


class AsyncRequestClientConnectionPool:
    """
    provides query and close methods
    """

    def __init__(
        self,
        client: Any,  # httpx.AsyncClient, imported lazily by the builder
        default_timeout: float,
        response_parser: Optional[Callable[[Any], Any]] = None,
        name: str = "" # Will be used as an identifier.
    ):
        if not name:
            raise ValueError("Name parameter can't be an empty string/None")
        self._name = name
        self._client = client
        self._default_timeout = default_timeout
        self._response_parser = response_parser or (lambda response: response.json())
        self.logger = get_logger(__name__)

    async def query(
        self,
        endpoint: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        content: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        response_parser: Optional[Callable[[Any], Any]] = None,
        method: str = "POST",
    ) -> Any:
        """
        Make an HTTP request to the inference server behind this pool.

        response_parser overrides how the raw response is converted for this call
        only (e.g. a non-Triton backend that isn't JSON) -- default is response.json(),
        matching the Triton KServe v2 convention.
        """
        try:
            response = await self._client.request(
                method,
                endpoint,
                json=json,
                content=content,
                headers=headers,
                timeout=timeout if timeout is not None else self._default_timeout,
            )
            if response.status_code == 404:
                raise LookupError(f"Endpoint:{endpoint}| not found for {self._name}")
            response.raise_for_status()
            return (response_parser or self._response_parser)(response)
        except LookupError:
            raise
        except Exception as e:
            # Log only the exception TYPE -- httpx/urllib3 error reprs embed the
            # request URL, which would leak the backend endpoint into any log sink.
            self.logger.error("%s connection pool query failed: %s", self._name, type(e).__name__)
            raise RuntimeError(f"{self._name} connection pool query failed") from e

    async def close(self) -> None:
        await self._client.aclose()


class AsyncRequestClientConnectionPoolBuilder:
    """
    Contains classmethods and data in the class, creates required connection session to the inference server
    upon calling the factory method.

    Config (_timeout/_max_connections/_max_keepalive_connections/_response_parser) is
    shared CLASS state mutated in place by the with_* methods -- every pool built from
    this class picks up whatever was set last. Fine while every build uses the same
    config (as init_connection_pool() does today); not safe for concurrent builds or
    giving two pools different settings.
    """

    _timeout: float = 300
    _max_connections: int = 100
    _max_keepalive_connections: int = 20
    _response_parser: Optional[Callable[[Any], Any]] = None

    @classmethod
    def with_timeout(cls, timeout: float):
        cls._timeout = timeout
        return cls

    @classmethod
    def with_pool_limits(cls, max_connections: int, max_keepalive_connections: int):
        cls._max_connections = max_connections
        cls._max_keepalive_connections = max_keepalive_connections
        return cls

    @classmethod
    def with_response_parser(cls, parser: Callable[[Any], Any]):
        cls._response_parser = parser
        return cls

    @classmethod
    def build_httpx_async_client(cls, name) -> AsyncRequestClientConnectionPool:
        client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(
                max_connections=cls._max_connections,
                max_keepalive_connections=cls._max_keepalive_connections,
            ),
        )
        return AsyncRequestClientConnectionPool(client, cls._timeout, cls._response_parser, name=name)


_HTTPX_ASYNC_GENERAL_CONNECTION_POOL: Optional[AsyncRequestClientConnectionPool] = None
_HTTPX_ASYNC_INFERENCE_CONNECTION_POOL: Optional[AsyncRequestClientConnectionPool] = None


def init_connection_pool():
    global _HTTPX_ASYNC_GENERAL_CONNECTION_POOL
    global _HTTPX_ASYNC_INFERENCE_CONNECTION_POOL

    from config import settings

    _HTTPX_ASYNC_GENERAL_CONNECTION_POOL = (
        AsyncRequestClientConnectionPoolBuilder
        .with_timeout(settings.DEFAULT_TRITON_TIMEOUT)
        .build_httpx_async_client("General")
    )

    _HTTPX_ASYNC_INFERENCE_CONNECTION_POOL = (
        AsyncRequestClientConnectionPoolBuilder
        .with_timeout(settings.DEFAULT_TRITON_TIMEOUT)
        .build_httpx_async_client("Inference")
    )



def get_general_connection_pool() -> AsyncRequestClientConnectionPool:
    if _HTTPX_ASYNC_GENERAL_CONNECTION_POOL is None:
        raise RuntimeError(
            "General connection pool not initialized; call init_connection_pool() first"
        )
    return _HTTPX_ASYNC_GENERAL_CONNECTION_POOL


def get_inference_connection_pool() -> AsyncRequestClientConnectionPool:
    if _HTTPX_ASYNC_INFERENCE_CONNECTION_POOL is None:
        raise RuntimeError(
            "Inference connection pool not initialized; call init_connection_pool() first"
        )
    return _HTTPX_ASYNC_INFERENCE_CONNECTION_POOL

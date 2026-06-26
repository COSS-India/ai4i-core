"""HTTP client utility for making external service API calls."""

from typing import Any, Dict, Optional
import logging
import httpx


logger = logging.getLogger(__name__)

_shared_async_client: Optional[httpx.AsyncClient] = None


def _get_shared_async_client(timeout: int) -> httpx.AsyncClient:
    """Reuse one AsyncClient per process for connection pooling to Triton/MMS."""
    global _shared_async_client
    if _shared_async_client is None:
        _shared_async_client = httpx.AsyncClient(timeout=timeout)
    return _shared_async_client


class HTTPServiceClient:
    """Reusable HTTP client for calling external services."""

    def __init__(self, timeout: int = 30):
        """
        Initialize HTTP service client.

        Args:
            timeout: Request timeout in seconds (default 30)
        """
        self.timeout = timeout

    async def get_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Make async GET request and return JSON response.

        Args:
            url: Full URL to call
            headers: Optional HTTP headers

        Returns:
            Response JSON as dictionary

        Raises:
            LookupError: If endpoint returns 404
            ConnectionError: If request fails or returns error status
        """
        try:
            client = _get_shared_async_client(self.timeout)
            response = await client.get(
                url,
                headers=headers or {},
            )

            if response.status_code == 404:
                logger.warning(f"Service endpoint not found: {url}")
                raise LookupError(f"Endpoint not found: {url}")

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {url}: {e.response.status_code}")
            raise ConnectionError(f"HTTP {e.response.status_code} from {url}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {url}: {str(e)}")
            raise ConnectionError(f"Request failed to {url}: {str(e)}") from e

    async def post_json(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Make async POST request with JSON body and return JSON response.

        Args:
            url: Full URL to call
            data: JSON data to send
            headers: Optional HTTP headers

        Returns:
            Response JSON as dictionary

        Raises:
            LookupError: If endpoint returns 404
            ConnectionError: If request fails or returns error status
        """
        try:
            client = _get_shared_async_client(self.timeout)
            response = await client.post(
                url,
                json=data,
                headers=headers or {},
            )

            if response.status_code == 404:
                logger.warning(f"Service endpoint not found: {url}")
                raise LookupError(f"Endpoint not found: {url}")

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {url}: {e.response.status_code}")
            raise ConnectionError(f"HTTP {e.response.status_code} from {url}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {url}: {str(e)}")
            raise ConnectionError(f"Request failed to {url}: {str(e)}") from e

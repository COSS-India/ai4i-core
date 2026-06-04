"""HTTP client utility for making external service API calls."""

from typing import Any, Dict, Optional
import logging
import httpx


logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Base exception for HTTP client errors."""

    pass


class ServiceCallError(HTTPClientError):
    """Raised when external service call fails."""

    pass


class ServiceNotFoundError(HTTPClientError):
    """Raised when service endpoint returns 404."""

    pass


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
            ServiceNotFoundError: If endpoint returns 404
            ServiceCallError: If request fails or returns error status
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=headers or {},
                    timeout=self.timeout,
                )

                if response.status_code == 404:
                    logger.warning(f"Service endpoint not found: {url}")
                    raise ServiceNotFoundError(f"Endpoint not found: {url}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {url}: {e.response.status_code}")
            raise ServiceCallError(f"HTTP {e.response.status_code} from {url}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {url}: {str(e)}")
            raise ServiceCallError(f"Request failed to {url}: {str(e)}") from e

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
            ServiceNotFoundError: If endpoint returns 404
            ServiceCallError: If request fails or returns error status
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers=headers or {},
                    timeout=self.timeout,
                )

                if response.status_code == 404:
                    logger.warning(f"Service endpoint not found: {url}")
                    raise ServiceNotFoundError(f"Endpoint not found: {url}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {url}: {e.response.status_code}")
            raise ServiceCallError(f"HTTP {e.response.status_code} from {url}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {url}: {str(e)}")
            raise ServiceCallError(f"Request failed to {url}: {str(e)}") from e

"""
SMR (Service Model Router) integration service for TTS.

Handles:
 - resolve_service_id  -- call SMR when serviceId is not in the request
 - call_smr            -- raw HTTP call to the SMR select-service endpoint
 - switch_to_fallback  -- resolve fallback service endpoint via Model Management
"""

import logging
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import HTTPException, Request

from ai4icore_env import app_env
from ai4icore_constants.error_messages import SERVICE_UNPUBLISHED, SERVICE_UNPUBLISHED_MESSAGE

logger = logging.getLogger(__name__)

SMR_SERVICE_URL = app_env.smr_service_url
SMR_ENABLED = getattr(app_env, "smr_enabled", True)


class SMRService:
    """Encapsulates all SMR / fallback-service interactions for TTS."""

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def resolve_service_id(
        self,
        request,  # TTSInferenceRequest (Pydantic model)
        http_request: Request,
    ) -> Optional[Dict[str, Any]]:
        """Resolve serviceId via SMR when it is missing from the request body.

        Returns the SMR response dict if SMR was called, otherwise ``None``.
        Side-effects: sets ``request.config.serviceId``, ``http_request.state.*``
        attributes needed by downstream dependencies.
        """
        if request.config.serviceId:
            return None

        if not SMR_ENABLED:
            return None

        user_id = getattr(http_request.state, "user_id", None)

        # Only use tenant_id from JWT (not fallback lookup)
        jwt_payload = getattr(http_request.state, "jwt_payload", None)
        tenant_id = jwt_payload.get("tenant_id") if jwt_payload else None

        logger.info(
            "serviceId not provided, calling SMR service",
            extra={"user_id": user_id, "tenant_id": tenant_id},
        )

        # Serialise the request body
        try:
            request_body = request.model_dump(exclude_none=False)
        except AttributeError:
            request_body = request.dict(exclude_none=False)

        smr_response_data = await self.call_smr(
            request_body=request_body,
            user_id=str(user_id) if user_id else None,
            tenant_id=str(tenant_id) if tenant_id else None,
            http_request=http_request,
        )

        service_id = smr_response_data.get("serviceId")
        if not service_id:
            raise HTTPException(
                status_code=500,
                detail={"code": "SMR_NO_SERVICE_ID", "message": "SMR service did not return a serviceId"},
            )

        # Store fallback service ID if present
        fallback_service_id = smr_response_data.get("fallbackServiceId")
        if fallback_service_id:
            http_request.state.fallback_service_id = fallback_service_id

        # ── Normal path: set serviceId and resolve endpoint ──
        request.config.serviceId = service_id
        http_request.state.service_id = service_id

        await self._resolve_endpoint_for_service(service_id, http_request)

        http_request.state.smr_response_data = smr_response_data

        # Verify endpoint was resolved
        if not getattr(http_request.state, "triton_endpoint", None):
            model_mgmt_error = getattr(http_request.state, "model_management_error", None)
            error_msg = f"Failed to resolve Triton endpoint for serviceId: {service_id}"
            if model_mgmt_error:
                error_msg += f". {model_mgmt_error}"
            error_detail: Dict[str, Any] = {
                "code": "ENDPOINT_RESOLUTION_FAILED",
                "message": error_msg,
            }
            if smr_response_data:
                error_detail["smr_response"] = smr_response_data
            raise HTTPException(status_code=500, detail=error_detail)

        return smr_response_data

    # ──────────────────────────────────────────────

    async def call_smr(
        self,
        request_body: Dict[str, Any],
        user_id: Optional[str],
        tenant_id: Optional[str],
        http_request: Request,
    ) -> Dict[str, Any]:
        """Call the SMR select-service endpoint and return the JSON response."""
        try:
            headers = dict(http_request.headers)

            # Extract policy & forwarding headers
            latency_policy = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
            cost_policy = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
            accuracy_policy = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")
            request_profiler_header = headers.get("X-Request-Profiler") or headers.get("x-request-profiler")

            smr_payload = {
                "task_type": "tts",
                "request_body": request_body,
                "user_id": user_id,
                "tenant_id": tenant_id,
            }

            smr_headers: Dict[str, str] = {}
            if "Authorization" in headers:
                smr_headers["Authorization"] = headers["Authorization"]
            if "X-API-Key" in headers:
                smr_headers["X-API-Key"] = headers["X-API-Key"]
            if latency_policy:
                smr_headers["X-Latency-Policy"] = latency_policy
            if cost_policy:
                smr_headers["X-Cost-Policy"] = cost_policy
            if accuracy_policy:
                smr_headers["X-Accuracy-Policy"] = accuracy_policy
            if request_profiler_header:
                smr_headers["X-Request-Profiler"] = request_profiler_header

            logger.info(
                "Calling SMR service to get serviceId",
                extra={
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "has_policy_headers": bool(latency_policy or cost_policy or accuracy_policy),
                },
            )

            bypass_cache = getattr(app_env, "bypass_cache", False)
            if bypass_cache:
                smr_headers["X-Bypass-Cache"] = "true"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{SMR_SERVICE_URL}/api/v1/smr/select-service",
                    json=smr_payload,
                    headers=smr_headers,
                )
                response.raise_for_status()
                smr_response = response.json()

            logger.info(
                "SMR service returned serviceId",
                extra={"service_id": smr_response.get("serviceId")},
            )
            return smr_response

        except httpx.HTTPStatusError as e:
            logger.error("SMR service returned error status", exc_info=True)
            error_detail = None
            try:
                error_response = e.response.json()
                error_detail = error_response.get("detail", {})
            except (ValueError, KeyError):
                pass

            if error_detail and isinstance(error_detail, dict) and error_detail.get("code") == "INVALID_POLICY_COMBINATION":
                raise HTTPException(status_code=e.response.status_code, detail=error_detail) from e

            raise HTTPException(
                status_code=e.response.status_code,
                detail={"code": "SMR_SERVICE_ERROR", "message": f"SMR service returned error: {e.response.text}"},
            ) from e

        except httpx.RequestError as e:
            logger.error("SMR service request failed", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail={"code": "SMR_SERVICE_UNAVAILABLE", "message": "SMR service is temporarily unavailable. Please try again."},
            ) from e

        except Exception as e:
            logger.error("Unexpected error calling SMR service", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"code": "SMR_SERVICE_INTERNAL_ERROR", "message": f"Failed to call SMR service: {e}"},
            ) from e

    # ──────────────────────────────────────────────

    async def switch_to_fallback(
        self,
        request,  # TTSInferenceRequest
        http_request: Request,
        fallback_service_id: str,
    ) -> Tuple[str, str, str]:
        """Resolve fallback service endpoint via Model Management.

        Updates ``request.config.serviceId`` and ``http_request.state.*`` attributes,
        then returns ``(triton_endpoint, triton_api_key, triton_model_name)``.
        """
        logger.info(
            "TTS: Switching to fallback service",
            extra={"primary_service_id": request.config.serviceId, "fallback_service_id": fallback_service_id},
        )

        request.config.serviceId = fallback_service_id
        http_request.state.service_id = fallback_service_id

        model_management_client = getattr(http_request.app.state, "model_management_client", None)
        redis_client = getattr(http_request.app.state, "redis_client", None)

        if not model_management_client:
            raise HTTPException(
                status_code=500,
                detail={"code": "MODEL_MANAGEMENT_UNAVAILABLE", "message": "Model Management client not available for fallback service resolution"},
            )

        try:
            auth_headers = self._extract_auth_headers(http_request)
            bypass_cache = getattr(app_env, "bypass_cache", False)
            service_info = await model_management_client.get_service(
                service_id=fallback_service_id,
                use_cache=not bypass_cache,
                redis_client=redis_client,
                auth_headers=auth_headers,
            )

            if not service_info or not service_info.endpoint:
                raise HTTPException(
                    status_code=503,
                    detail={"code": "FALLBACK_SERVICE_UNAVAILABLE", "message": f"Fallback service {fallback_service_id} not found or has no endpoint configured"},
                )
            if service_info.is_published is not True:
                raise HTTPException(
                    status_code=403,
                    detail={"code": SERVICE_UNPUBLISHED, "message": SERVICE_UNPUBLISHED_MESSAGE, "serviceId": fallback_service_id},
                )

            triton_endpoint = service_info.endpoint
            triton_api_key = service_info.api_key or ""
            triton_model_name = self._model_name_from_service_info(service_info)

            http_request.state.triton_endpoint = triton_endpoint
            http_request.state.triton_api_key = triton_api_key
            http_request.state.triton_model_name = triton_model_name
            http_request.state.using_fallback_service = True

            logger.info(
                "TTS: Successfully switched to fallback service",
                extra={"fallback_service_id": fallback_service_id, "triton_endpoint": triton_endpoint, "triton_model_name": triton_model_name},
            )
            return triton_endpoint, triton_api_key, triton_model_name

        except HTTPException:
            raise
        except Exception as e:
            logger.error("TTS: Failed to resolve fallback service endpoint", extra={"fallback_service_id": fallback_service_id, "error": str(e)}, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"code": "FALLBACK_SERVICE_RESOLUTION_FAILED", "message": f"Failed to resolve endpoint for fallback service {fallback_service_id}: {e}"},
            ) from e

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    async def _resolve_endpoint_for_service(self, service_id: str, http_request: Request) -> None:
        """Resolve Triton endpoint via Model Management for a given service ID."""
        model_management_client = getattr(http_request.app.state, "model_management_client", None)
        redis_client = getattr(http_request.app.state, "redis_client", None)

        if not model_management_client:
            http_request.state.model_management_error = "Model Management client not available in application state"
            return

        try:
            auth_headers = self._extract_auth_headers(http_request)
            bypass_cache = getattr(app_env, "bypass_cache", False)
            service_info = await model_management_client.get_service(
                service_id=service_id,
                use_cache=not bypass_cache,
                redis_client=redis_client,
                auth_headers=auth_headers,
            )

            if not service_info:
                http_request.state.model_management_error = f"Service {service_id} not found in Model Management database"
                return
            if service_info.is_published is not True:
                raise HTTPException(
                    status_code=403,
                    detail={"code": SERVICE_UNPUBLISHED, "message": SERVICE_UNPUBLISHED_MESSAGE, "serviceId": service_id},
                )
            if not service_info.endpoint:
                http_request.state.model_management_error = f"Service {service_id} found but has no endpoint configured"
                return

            http_request.state.triton_endpoint = service_info.endpoint
            http_request.state.triton_api_key = service_info.api_key or ""
            http_request.state.triton_model_name = self._model_name_from_service_info(service_info)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error resolving Triton endpoint", extra={"service_id": service_id, "error": str(e)}, exc_info=True)
            http_request.state.model_management_error = str(e)
            if "401" in str(e) or "403" in str(e) or "404" in str(e):
                raise HTTPException(
                    status_code=500,
                    detail={"code": "MODEL_MANAGEMENT_ERROR", "message": f"Failed to resolve endpoint for serviceId {service_id}: {e}"},
                ) from e

    @staticmethod
    def _model_name_from_service_info(service_info) -> str:
        """Extract triton model name from a ServiceInfo object."""
        if service_info.model_inference_endpoint:
            ie = service_info.model_inference_endpoint
            if isinstance(ie, dict):
                return (
                    ie.get("model_name")
                    or ie.get("modelName")
                    or ie.get("model")
                    or service_info.triton_model
                    or service_info.model_name
                    or "unknown"
                )
        if service_info.model_name:
            return service_info.model_name
        if service_info.triton_model:
            return service_info.triton_model
        return "unknown"

    @staticmethod
    def _extract_auth_headers(request: Request) -> Dict[str, str]:
        """Extract authentication headers from the incoming request."""
        auth_headers: Dict[str, str] = {}
        authorization = request.headers.get("Authorization") or request.headers.get("authorization")
        if authorization:
            auth_headers["Authorization"] = authorization
        x_api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if x_api_key:
            auth_headers["X-API-Key"] = x_api_key
        x_auth_source = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
        if x_auth_source:
            auth_headers["X-Auth-Source"] = x_auth_source
        return auth_headers

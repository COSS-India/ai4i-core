"""
Business-logic service for the Service domain.

Owns the rules:
- Service IDs are deterministic SHA256 hashes of the service name only.
- Service names must be globally unique.
- A service must reference an existing (model_id, model_version).
- The endpoint URL is validated (URL format + SSRF + live probe) on
  create/update.
- Published services are immutable and cannot be deleted; they must be
  unpublished first.
- name, modelId, modelVersion are not updatable.
- Policy combinations are validated (e.g., low-cost + sensitive accuracy).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    EntityNotFoundError,
    ValidationError,
)
from app.models.service import Service
from app.repositories.model_repository import ModelRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.service import (
    ServiceCreateRequest,
    ServicePolicy,
    ServiceUpdateRequest,
)
from app.services.cache_service import CacheService
from app.services.serializers import (
    service_detail_dict,
    service_to_dict,
)
from app.utils.endpoint_validator import ValidationStatus, validate_endpoint
from app.utils.hashing import generate_service_id

logger = logging.getLogger(__name__)


class DuplicateServiceNameError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="DUPLICATE_SERVICE_NAME", status_code=409
        )


class PublishedServiceImmutableError(AppError):
    """Raised on attempts to delete a still-published service."""

    def __init__(self, service_id: str) -> None:
        super().__init__(
            message=(
                f"Service '{service_id}' cannot be deleted because it is "
                "currently published. Unpublish the service first to delete it."
            ),
            code="PUBLISHED_SERVICE_IMMUTABLE",
            status_code=409,
        )


class EndpointValidationFailedError(AppError):
    def __init__(self, message: str, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(
            message=message, code="ENDPOINT_VALIDATION_ERROR", status_code=400
        )


def _extract_validation_params(model_inference_endpoint: Dict[str, Any]) -> Dict[str, Any]:
    """Pull task_type / request_schema / triton_schema out of a model card."""
    schema = (model_inference_endpoint or {}).get("schema") or {}
    return {
        "request_schema": schema.get("request"),
        "triton_schema": (schema.get("response") or {}).get("triton"),
    }


def _validate_policy(policy: ServicePolicy) -> None:
    """Cross-field policy constraints.

    These mirror the gateway's request-time validation so invalid combinations
    cannot be persisted in the platform.
    """
    latency = policy.latency.value if policy.latency else None
    cost = policy.cost.value if policy.cost else None
    accuracy = policy.accuracy.value if policy.accuracy else None

    if cost == "tier_1":
        if accuracy == "sensitive":
            raise ValidationError(
                message=(
                    "Requested combination accuracy='sensitive' with "
                    "cost='tier_1' is against policy. Choose a higher cost "
                    "tier or lower accuracy profile."
                ),
                code="POLICY_CONSTRAINT_VIOLATION",
            )
        if latency == "low":
            raise ValidationError(
                message=(
                    "Requested combination latency='low' with cost='tier_1' "
                    "is against policy. Choose a higher cost tier or higher "
                    "latency profile."
                ),
                code="POLICY_CONSTRAINT_VIOLATION",
            )


class ServiceService:
    """Application-level service orchestrating service use-cases."""

    def __init__(
        self,
        service_repo: ServiceRepository,
        model_repo: ModelRepository,
        cache: CacheService,
    ) -> None:
        self._services = service_repo
        self._models = model_repo
        self._cache = cache

    # ── Reads ──

    async def get_service_detail(self, service_id: str) -> Dict[str, Any]:
        cached = await self._cache.get_service(service_id)
        if cached:
            return cached

        service = await self._services.get_by_service_id(service_id)
        if service is None:
            try:
                service = await self._services.get_by_uuid(UUID(service_id))
            except (ValueError, TypeError):
                service = None
        if service is None:
            raise EntityNotFoundError(f"Service '{service_id}'")

        model = await self._models.get_by_id_version(service.model_id, service.model_version)
        if model is None:
            raise EntityNotFoundError(
                f"Model '{service.model_id}' v{service.model_version}"
            )

        data = service_detail_dict(service, model)
        await self._cache.set_service(service.service_id, data)
        return data

    async def list_services(
        self,
        *,
        task_type: Optional[str] = None,
        is_published: Optional[bool] = None,
        created_by: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        rows = await self._services.list_services(
            task_type=task_type,
            is_published=is_published,
            created_by=created_by,
            offset=offset,
            limit=limit,
        )
        items = [
            service_to_dict(service, model=model, include_task_languages=True)
            for service, model in rows
        ]
        if offset > 0 or limit is not None:
            total = await self._services.count_services(
                task_type=task_type,
                is_published=is_published,
                created_by=created_by,
            )
        else:
            total = len(items)
        return items, total

    # ── Writes ──

    async def create_service(
        self, payload: ServiceCreateRequest, *, created_by: Optional[str]
    ) -> str:
        # 1. Look up the referenced model
        model = await self._models.get_by_id_version(payload.modelId, payload.modelVersion)
        if model is None:
            raise ValidationError(
                message=(
                    f"Model with ID '{payload.modelId}' version "
                    f"'{payload.modelVersion}' not found. Cannot create service."
                ),
                code="MODEL_NOT_FOUND",
            )

        # 2. Validate the endpoint (live probe + SSRF guard)
        await self._validate_endpoint_for_model(
            endpoint=payload.endpoint,
            api_key=payload.api_key,
            model_inference_endpoint=model.inference_endpoint or {},
            task_type=(model.task or {}).get("type"),
        )

        # 3. Duplicate name check
        if await self._services.get_by_name(payload.name):
            raise DuplicateServiceNameError(
                f"Service with name '{payload.name}' already exists."
            )

        # 4. Persist
        service_id = generate_service_id(payload.name)
        is_published = bool(payload.isPublished)
        now = datetime.now(timezone.utc) if is_published else None
        instance = Service(
            service_id=service_id,
            name=payload.name,
            service_description=payload.serviceDescription,
            hardware_description=payload.hardwareDescription,
            model_id=payload.modelId,
            model_version=payload.modelVersion,
            endpoint=payload.endpoint,
            inference_server_type=(
                payload.inferenceServerType.value
                if payload.inferenceServerType
                else "triton"
            ),
            ssl_verify=payload.sslVerify,
            api_key=payload.api_key,
            health_status=jsonable_encoder(payload.healthStatus) if payload.healthStatus else {},
            benchmarks=jsonable_encoder(payload.benchmarks) if payload.benchmarks else None,
            is_published=is_published,
            published_at=now,
            created_by=created_by,
        )
        try:
            await self._services.add(instance)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error creating service")
            raise

        # 5. Warm cache
        data = service_detail_dict(instance, model)
        await self._cache.set_service(instance.service_id, data)
        logger.info("Created service '%s' (id=%s)", payload.name, service_id)
        return service_id

    async def update_service(
        self, payload: ServiceUpdateRequest, *, updated_by: Optional[str]
    ) -> None:
        if not payload.serviceId:
            raise ValidationError(
                message="serviceId is required.",
                code="SERVICE_ID_REQUIRED",
            )

        instance = await self._services.get_by_service_id(payload.serviceId)
        if instance is None:
            raise EntityNotFoundError(f"Service '{payload.serviceId}'")

        # If endpoint changes, re-validate it against the model schema
        if payload.endpoint:
            model = await self._models.get_by_id_version(
                instance.model_id, instance.model_version
            )
            if model is None:
                raise EntityNotFoundError(
                    f"Model '{instance.model_id}' v{instance.model_version}"
                )
            api_key = payload.api_key or instance.api_key
            await self._validate_endpoint_for_model(
                endpoint=payload.endpoint,
                api_key=api_key,
                model_inference_endpoint=model.inference_endpoint or {},
                task_type=(model.task or {}).get("type"),
            )

        request_dict = payload.model_dump(exclude_unset=True)
        update_data: Dict[str, Any] = {}

        if "serviceDescription" in request_dict:
            update_data["service_description"] = request_dict["serviceDescription"]
        if "hardwareDescription" in request_dict:
            update_data["hardware_description"] = request_dict["hardwareDescription"]
        if "endpoint" in request_dict:
            update_data["endpoint"] = request_dict["endpoint"]
        if request_dict.get("inferenceServerType") is not None:
            ist = request_dict["inferenceServerType"]
            update_data["inference_server_type"] = (
                ist.value if hasattr(ist, "value") else ist
            )
        if request_dict.get("sslVerify") is not None:
            update_data["ssl_verify"] = bool(request_dict["sslVerify"])
        if "api_key" in request_dict:
            update_data["api_key"] = request_dict["api_key"]
        if "healthStatus" in request_dict:
            update_data["health_status"] = request_dict["healthStatus"]
        if "benchmarks" in request_dict:
            update_data["benchmarks"] = jsonable_encoder(request_dict["benchmarks"])

        if "policy" in request_dict:
            policy_obj = payload.policy
            if policy_obj is not None:
                _validate_policy(policy_obj)
                policy_dict: Optional[Dict[str, Any]] = {
                    k: (v.value if hasattr(v, "value") else v)
                    for k, v in policy_obj.model_dump(exclude_none=True).items()
                }
            else:
                policy_dict = None
            update_data["policy"] = policy_dict

        if "isPublished" in request_dict:
            now = datetime.now(timezone.utc)
            is_pub = bool(request_dict["isPublished"])
            update_data["is_published"] = is_pub
            if is_pub:
                update_data["published_at"] = now
                update_data["unpublished_at"] = None
            else:
                update_data["unpublished_at"] = now

        if updated_by is not None:
            update_data["updated_by"] = updated_by

        if not update_data:
            raise ValidationError(
                message=(
                    "No valid update fields provided. Updatable fields: "
                    "serviceDescription, hardwareDescription, endpoint, "
                    "inferenceServerType, sslVerify, api_key, healthStatus, "
                    "benchmarks, isPublished, policy. Note: name, modelId, "
                    "modelVersion are not updatable."
                ),
                code="NO_UPDATABLE_FIELDS",
            )

        try:
            await self._services.apply_updates(instance, update_data)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error updating service")
            raise

        # Refresh cache (eager rebuild)
        await self._cache.invalidate_service(instance.service_id)
        model = await self._models.get_by_id_version(
            instance.model_id, instance.model_version
        )
        if model is not None:
            await self._cache.set_service(
                instance.service_id, service_detail_dict(instance, model)
            )

    async def delete_service(self, id_str: str) -> None:
        try:
            uuid = UUID(id_str)
        except ValueError:
            raise EntityNotFoundError(f"Service '{id_str}'")

        instance = await self._services.get_by_uuid(uuid)
        if instance is None:
            raise EntityNotFoundError(f"Service '{id_str}'")
        if instance.is_published:
            raise PublishedServiceImmutableError(instance.service_id)

        try:
            await self._services.delete_by_uuid(uuid)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error deleting service")
            raise

        await self._cache.invalidate_service(instance.service_id)
        logger.info("Deleted service %s", instance.service_id)

    # ── Internals ──

    async def _validate_endpoint_for_model(
        self,
        *,
        endpoint: str,
        api_key: Optional[str],
        model_inference_endpoint: Dict[str, Any],
        task_type: Optional[str],
    ) -> None:
        params = _extract_validation_params(model_inference_endpoint)
        result = await validate_endpoint(
            endpoint=endpoint,
            task_type=task_type,
            request_schema=params["request_schema"],
            triton_schema=params["triton_schema"],
            api_key=api_key or None,
            run_inference_test=settings.run_inference_test,
            timeout=settings.endpoint_validation_timeout_seconds,
            validation_mode=settings.endpoint_validation_mode,
            skip_tls_verify=settings.endpoint_validation_skip_tls_verify,
        )
        if not result.is_valid:
            failed_messages = [
                d.message for d in result.details if d.status == ValidationStatus.FAILED
            ]
            raise EndpointValidationFailedError(
                message="Service endpoint validation failed.",
                errors=failed_messages,
            )

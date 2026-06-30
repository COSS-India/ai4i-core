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
- Policy fields (latency/cost/accuracy) are stored as-is; combination enforcement is the gateway's responsibility.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi.encoders import jsonable_encoder
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    EntityNotFoundError,
    ValidationError,
)
from app.models.model_management.service import Service
from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.schemas.model_management.service import (
    ServiceCreateRequest,
    ServiceUpdateRequest,
)
from app.services.cache_service import CacheService
from .serializers import (
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


_PPU_REDIS_KEY_PREFIX = "ppu:svc:"
_PPU_REDIS_TTL = 3600  # 1 hour


class ServiceService:
    """Application-level service orchestrating service use-cases."""

    def __init__(
        self,
        service_repo: ServiceRepository,
        model_repo: ModelRepository,
        cache: CacheService,
        redis: Optional[aioredis.Redis] = None,
    ) -> None:
        self._services = service_repo
        self._models = model_repo
        self._cache = cache
        self._redis = redis

    async def _write_ppu_pricing(self, instance: "Service") -> None:
        """Write PPU pricing for a service to Redis so the inference service can read it."""
        if self._redis is None:
            return
        if not any([instance.billing_unit_type, instance.cost_per_unit, instance.unit_rate]):
            return
        pricing = {
            "billing_unit_type": instance.billing_unit_type,
            "cost_per_unit": float(instance.cost_per_unit) if instance.cost_per_unit is not None else None,
            "unit_size": instance.unit_size,
            "unit_rate": float(instance.unit_rate) if instance.unit_rate is not None else None,
        }
        key = f"{_PPU_REDIS_KEY_PREFIX}{instance.service_id}"
        try:
            await self._redis.set(key, json.dumps(pricing), ex=_PPU_REDIS_TTL)
            logger.debug("Wrote PPU pricing to Redis key=%s", key)
        except Exception:
            logger.warning("Failed to write PPU pricing to Redis for service_id=%s", instance.service_id, exc_info=True)

    async def _delete_ppu_pricing(self, service_id: str) -> None:
        """Remove PPU pricing key from Redis when a service is deleted."""
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"{_PPU_REDIS_KEY_PREFIX}{service_id}")
        except Exception:
            logger.warning("Failed to delete PPU pricing from Redis for service_id=%s", service_id, exc_info=True)

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

        tier_name_map = await self._services.get_tier_names_by_ids(service.tier_ids or [])
        tier_names = [tier_name_map.get(tid) for tid in service.tier_ids] if service.tier_ids else None
        data = service_detail_dict(service, model, tier_names=tier_names)
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
        all_tier_ids = list({tid for svc, _ in rows for tid in (svc.tier_ids or [])})
        tier_name_map = await self._services.get_tier_names_by_ids(all_tier_ids)
        items = [
            service_to_dict(
                service,
                model=model,
                include_task_languages=True,
                tier_names=[tier_name_map.get(tid) for tid in service.tier_ids] if service.tier_ids else None,
            )
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
        unit_rate = (
            payload.costPerUnit / payload.unitSize
            if payload.costPerUnit is not None and payload.unitSize is not None
            else None
        )
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
            billing_unit_type=payload.billingUnitType,
            cost_per_unit=payload.costPerUnit,
            unit_size=payload.unitSize,
            unit_rate=unit_rate,
            tier_ids=payload.tierIds,
            created_by=created_by,
        )
        try:
            await self._services.add(instance)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error creating service")
            raise

        # 5. Warm cache + publish PPU pricing to Redis
        tier_name_map = await self._services.get_tier_names_by_ids(instance.tier_ids or [])
        tier_names = [tier_name_map.get(tid) for tid in instance.tier_ids] if instance.tier_ids else None
        data = service_detail_dict(instance, model, tier_names=tier_names)
        await self._cache.set_service(instance.service_id, data)
        await self._write_ppu_pricing(instance)
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

        if "billingUnitType" in request_dict:
            update_data["billing_unit_type"] = request_dict["billingUnitType"]
        if "costPerUnit" in request_dict:
            update_data["cost_per_unit"] = request_dict["costPerUnit"]
        if "unitSize" in request_dict:
            update_data["unit_size"] = request_dict["unitSize"]
        if "tierIds" in request_dict:
            update_data["tier_ids"] = request_dict["tierIds"]

        # Recompute unit_rate whenever either factor changes.
        if "cost_per_unit" in update_data or "unit_size" in update_data:
            new_cost = update_data.get("cost_per_unit", instance.cost_per_unit)
            new_size = update_data.get("unit_size", instance.unit_size)
            update_data["unit_rate"] = (
                float(new_cost) / int(new_size)
                if new_cost is not None and new_size is not None and int(new_size) > 0
                else None
            )

        if updated_by is not None:
            update_data["updated_by"] = updated_by

        if not update_data:
            raise ValidationError(
                message=(
                    "No valid update fields provided. Updatable fields: "
                    "serviceDescription, hardwareDescription, endpoint, "
                    "inferenceServerType, sslVerify, api_key, healthStatus, "
                    "benchmarks, isPublished, policy, billingUnitType, "
                    "costPerUnit, unitSize, tierIds. Note: name, modelId, "
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

        # Refresh cache (eager rebuild) + sync PPU pricing to Redis
        await self._cache.invalidate_service(instance.service_id)
        model = await self._models.get_by_id_version(
            instance.model_id, instance.model_version
        )
        if model is not None:
            tier_name_map = await self._services.get_tier_names_by_ids(instance.tier_ids or [])
            tier_names = [tier_name_map.get(tid) for tid in instance.tier_ids] if instance.tier_ids else None
            await self._cache.set_service(
                instance.service_id, service_detail_dict(instance, model, tier_names=tier_names)
            )
        if any(k in update_data for k in ("billing_unit_type", "cost_per_unit", "unit_size", "unit_rate")):
            await self._write_ppu_pricing(instance)

    async def delete_service(self, id_str: str) -> None:
        instance = await self._services.get_by_service_id(id_str)
        if instance is None:
            raise EntityNotFoundError(f"Service '{id_str}'")
        if instance.is_published:
            raise PublishedServiceImmutableError(instance.service_id)

        try:
            await self._services.delete_by_service_id(instance.service_id)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error deleting service")
            raise

        await self._cache.invalidate_service(instance.service_id)
        await self._delete_ppu_pricing(instance.service_id)
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

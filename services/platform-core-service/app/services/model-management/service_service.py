"""
Business-logic service for the Service domain.

Owns the rules:
- Service IDs are user-supplied, alphanumeric (/ - _ allowed), and must be globally unique.
- Service names must be globally unique.
- A service must reference an existing (model_id, model_version).
- The endpoint URL is validated (URL format + SSRF + live probe) on
  create/update, and the pollingUrl of async models gets the same SSRF
  check before it's ever POSTed to. The live probe also checks the actual
  response's shape: expectedResponseSchema is an optional per-service
  override; when omitted, a built-in per-task-type default is used
  (app/utils/probe_payloads.get_expected_response_shape), and task types
  with no known default simply skip the shape check. Supplying a new
  expectedResponseSchema on update — even without an endpoint change —
  re-probes the current endpoint with it before it's stored, so a schema is
  never persisted without having been checked against a live response.
  Sync vs. async (poll-until-done) probing is decided by the referenced
  model's isSyncApi/asyncApiDetails.
- Published services are immutable and cannot be deleted; they must be
  unpublished first.
- name, modelId, modelVersion are not updatable.
- Policy fields (latency/cost/accuracy) are stored as-is; combination enforcement is the gateway's responsibility.
"""

import asyncio
import functools
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError

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
    ServiceEndpointUpdateItem,
    ServiceUpdateRequest,
    schema_matches_task_type,
    validate_inference_schema_entries,
)
from app.services.cache_service import CacheService
from .serializers import (
    service_detail_dict,
    service_to_dict,
)
from app.utils.endpoint_validator import ValidationStatus, validate_endpoint
from app.utils.security import sanitize_url_for_log

logger = logging.getLogger(__name__)


class DuplicateServiceNameError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="DUPLICATE_SERVICE_NAME", status_code=409
        )


class DuplicateServiceIdError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="DUPLICATE_SERVICE_ID", status_code=409
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


def _log_rejections(
    func: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[Any]]:
    """Log any client-facing rejection raised inside *func* before it
    propagates.

    Nothing else records these. The shared handlers in ai4i_core log only
    unhandled exceptions, and RequestMiddleware skips 4xx to avoid
    duplicating the gateway's access log. Without this a rejected create,
    update or delete leaves no trace in the pod at all, and the caller's
    error toast is the only evidence it happened.

    Applied at the method boundary rather than at each raise site so a
    rejection added later is covered without anyone remembering to log it.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except EndpointValidationFailedError:
            # Already logged by _validate_endpoint_for_model, with the
            # endpoint and task type this layer cannot see.
            raise
        except AppError as exc:
            logger.warning("Rejected %s: %s", exc.code, exc.message)
            raise

    return wrapper


def _extract_validation_params(model_inference_endpoint: Dict[str, Any]) -> Dict[str, Any]:
    """Pull request/response-schema and sync/async details out of a model card."""
    model_inference_endpoint = model_inference_endpoint or {}
    schema = model_inference_endpoint.get("schema") or {}
    async_details = model_inference_endpoint.get("asyncApiDetails") or {}
    # adapter_config migration (a1f2e3d4c5b6) writes the snake_case key into
    # this same inference_endpoint blob; inference_server_resolver.py reads
    # both spellings for the same reason — a card stored snake_case would
    # otherwise silently yield model_name=None here.
    adapter_config = (
        model_inference_endpoint.get("adapterConfig")
        or model_inference_endpoint.get("adapter_config")
        or {}
    )
    return {
        "request_schema": schema.get("request"),
        "triton_schema": (schema.get("response") or {}).get("triton"),
        "is_sync_api": model_inference_endpoint.get("isSyncApi"),
        "polling_url": async_details.get("pollingUrl"),
        "poll_interval_ms": async_details.get("pollInterval"),
        # Authoritative real model identifier for LLM (OpenAI-compatible)
        # deployments — schema.request.model is only a sample the admin
        # typed in and has repeatedly been found stale/wrong in practice
        # (AI4IDS-1844 follow-up); the probe payload builder prefers this
        # over anything in schema.request. An upcoming model-schema change
        # is expected to drop "model" from schema.request entirely, so this
        # is the durable source going forward, not a fallback.
        "model_name": adapter_config.get("model_name"),
    }


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
        cached = self._cache.get_service(service_id)
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
        self._cache.set_service(service.service_id, data)
        return data

    async def list_services(
        self,
        *,
        task_types: Optional[List[str]] = None,
        is_published: Optional[bool] = None,
        created_by: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        rows = await self._services.list_services(
            task_types=task_types,
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
                task_types=task_types,
                is_published=is_published,
                created_by=created_by,
            )
        else:
            total = len(items)
        return items, total

    # ── Writes ──

    @_log_rejections
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

        # 2. Validate the endpoint (live probe + SSRF guard + response shape)
        await self._validate_endpoint_for_model(
            endpoint=payload.endpoint,
            api_key=payload.api_key,
            model_inference_endpoint=model.inference_endpoint or {},
            task_type=(model.task or {}).get("type"),
            expected_response_schema=payload.expectedResponseSchema,
        )

        # 3. Duplicate name check
        if await self._services.get_by_name(payload.name):
            raise DuplicateServiceNameError(
                f"Service with name '{payload.name}' already exists."
            )

        # 4. Duplicate service ID check
        if await self._services.get_by_service_id(payload.serviceId):
            raise DuplicateServiceIdError(
                f"Service with ID '{payload.serviceId}' already exists."
            )

        # 5. Every tierId must reference an existing PPU tier
        await self._validate_tier_ids_exist(payload.tierIds)

        # 5b. Resolve inferenceEndPoint.schema: supplied value wins,
        # otherwise derive from the linked model's own schema.
        effective_schema = self._resolve_inference_schema(
            payload.inferenceEndPoint.endpoint_schema, model, task_type=payload.taskType,
        )

        # 6. Persist
        service_id = payload.serviceId
        unit_rate = (
            payload.costPerUnit / payload.unitSize
            if payload.costPerUnit is not None and payload.unitSize is not None
            else None
        )
        # `_reconcile_ulca_fields` on ServiceCreateRequest has
        # already merged the deprecated flat aliases and the new nested
        # `inferenceEndPoint`/`task` fields into one another, and guarantees
        # `inferenceEndPoint` is populated here — so the net-new ULCA fields
        # below always have a home to read from regardless of which input
        # shape the caller actually used.
        ep = payload.inferenceEndPoint
        instance = Service(
            service_id=service_id,
            name=payload.name,
            service_description=payload.description,
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
            inference_api_key=jsonable_encoder(ep.inferenceApiKey) if ep.inferenceApiKey else None,
            inference_schema=jsonable_encoder(effective_schema),
            is_sync_api=ep.isSyncApi,
            async_api_details=jsonable_encoder(ep.asyncApiDetails) if ep.asyncApiDetails else None,
            is_multilingual_enabled=bool(ep.isMultilingualEnabled),
            supported_input_formats=jsonable_encoder(ep.supportedInputFormats) if ep.supportedInputFormats else None,
            supported_output_formats=jsonable_encoder(ep.supportedOutputFormats) if ep.supportedOutputFormats else None,
            provider_name=ep.providerName,
            inference_model_id=ep.inferenceModelId,
            health_status=jsonable_encoder(payload.healthStatus) if payload.healthStatus else {},
            benchmarks=jsonable_encoder(payload.benchmarks) if payload.benchmarks else None,
            expected_response_schema=jsonable_encoder(payload.expectedResponseSchema),
            task_type=payload.taskType,
            cost_per_unit=payload.costPerUnit,
            unit_size=payload.unitSize,
            unit_rate=unit_rate,
            tier_ids=payload.tierIds,
            created_by=created_by,
        )
        try:
            await self._services.add(instance)
            await self._services.commit()
        except IntegrityError as exc:
            await self._services.rollback()
            constraint = str(exc.orig)
            if "uq_mm_services_service_id" in constraint:
                raise DuplicateServiceIdError(
                    f"Service with ID '{payload.serviceId}' already exists."
                )
            if "uq_mm_services_name" in constraint:
                raise DuplicateServiceNameError(
                    f"Service with name '{payload.name}' already exists."
                )
            logger.exception("DB integrity error creating service")
            raise
        except Exception:
            await self._services.rollback()
            logger.exception("DB error creating service")
            raise

        # 7. Warm cache
        tier_name_map = await self._services.get_tier_names_by_ids(instance.tier_ids or [])
        tier_names = [tier_name_map.get(tid) for tid in instance.tier_ids] if instance.tier_ids else None
        data = service_detail_dict(instance, model, tier_names=tier_names)
        self._cache.set_service(instance.service_id, data)
        logger.info("Created service '%s' (id=%s)", payload.name, service_id)
        return service_id

    @_log_rejections
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

        # Catch a taskType/schema mismatch even when only one side of the
        # pair is being changed in this update (the Pydantic-layer check on
        # ServiceUpdateRequest only catches it when both are touched
        # together in the same payload, since it has no access to what's
        # currently stored).
        self._validate_schema_task_type_consistency_on_update(
            new_task_type=payload.taskType,
            new_schema=(
                payload.inferenceEndPoint.endpoint_schema
                if payload.inferenceEndPoint is not None
                else None
            ),
            existing_task_type=instance.task_type,
            existing_schema=instance.inference_schema,
        )

        # Re-validate against the model schema whenever the endpoint changes,
        # or a new expectedResponseSchema is supplied on its own — the latter
        # is probed against the (possibly unchanged) live endpoint before
        # being trusted/stored, so a schema is never persisted without ever
        # having been checked against a real response. Neither field is
        # required: with nothing supplied or on file, validate_endpoint()
        # falls back to the task-type default shape (or skips the shape
        # check entirely for a task type with no known default).
        if payload.endpoint or payload.expectedResponseSchema is not None:
            model = await self._models.get_by_id_version(
                instance.model_id, instance.model_version
            )
            if model is None:
                raise EntityNotFoundError(
                    f"Model '{instance.model_id}' v{instance.model_version}"
                )
            api_key = payload.api_key or instance.api_key
            expected_response_schema = (
                payload.expectedResponseSchema
                if payload.expectedResponseSchema is not None
                else instance.expected_response_schema
            )
            await self._validate_endpoint_for_model(
                endpoint=payload.endpoint or instance.endpoint,
                api_key=api_key,
                model_inference_endpoint=model.inference_endpoint or {},
                task_type=(model.task or {}).get("type"),
                expected_response_schema=expected_response_schema,
            )

        request_dict = payload.model_dump(exclude_unset=True)
        update_data: Dict[str, Any] = {}

        # `_reconcile_ulca_fields` on ServiceUpdateRequest has
        # already backfilled `description`/`endpoint`/`hardwareDescription`/
        # `api_key`/`taskType` from the new `task`/`inferenceEndPoint`
        # fields (and vice versa) whenever either channel was touched, so
        # these checks cover both the deprecated flat input and the new
        # ULCA-shaped input without extra branching.
        if "description" in request_dict:
            update_data["service_description"] = request_dict["description"]
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
        if payload.inferenceEndPoint is not None:
            # Read straight off the validated object rather than
            # request_dict, so the `schema`-aliased field (attribute name
            # `endpoint_schema`) doesn't need special-casing here.
            ep = payload.inferenceEndPoint
            if ep.inferenceApiKey is not None:
                update_data["inference_api_key"] = jsonable_encoder(ep.inferenceApiKey)
            if ep.isMultilingualEnabled is not None:
                update_data["is_multilingual_enabled"] = ep.isMultilingualEnabled
            if ep.supportedInputFormats is not None:
                update_data["supported_input_formats"] = jsonable_encoder(ep.supportedInputFormats)
            if ep.supportedOutputFormats is not None:
                update_data["supported_output_formats"] = jsonable_encoder(ep.supportedOutputFormats)
            if ep.endpoint_schema is not None:
                update_data["inference_schema"] = jsonable_encoder(ep.endpoint_schema)
            if ep.isSyncApi is not None:
                update_data["is_sync_api"] = ep.isSyncApi
            if ep.asyncApiDetails is not None:
                update_data["async_api_details"] = jsonable_encoder(ep.asyncApiDetails)
            if ep.providerName is not None:
                update_data["provider_name"] = ep.providerName
            if ep.inferenceModelId is not None:
                update_data["inference_model_id"] = ep.inferenceModelId
        if "healthStatus" in request_dict:
            update_data["health_status"] = request_dict["healthStatus"]
        if "benchmarks" in request_dict:
            update_data["benchmarks"] = jsonable_encoder(request_dict["benchmarks"])
        if "expectedResponseSchema" in request_dict:
            update_data["expected_response_schema"] = jsonable_encoder(
                request_dict["expectedResponseSchema"]
            )

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

        if "isTryItDefault" in request_dict:
            is_default = bool(request_dict["isTryItDefault"])
            update_data["is_try_it_default"] = is_default
            if is_default and instance.task_type:
                # At most one default per task_type: clear the flag on every
                # other service of the same type before setting this one.
                #
                # task_type is nullable on the model (legacy rows predating
                # this column), so a None task_type intentionally skips this
                # invariant check rather than clearing across all null-typed
                # services. This is safe: Try-It only ever surfaces services
                # whose task_type is in _TRY_IT_SUPPORTED_TASK_TYPES (nmt/llm)
                # — see routes/service.py's list_try_it_services — so a
                # None-task_type service's is_try_it_default value can never
                # be read by the Try-It flow regardless.
                await self._services.clear_try_it_default(
                    task_type=instance.task_type,
                    exclude_service_id=instance.service_id,
                )

        if "taskType" in request_dict:
            update_data["task_type"] = request_dict["taskType"]
        if "costPerUnit" in request_dict:
            update_data["cost_per_unit"] = request_dict["costPerUnit"]
        if "unitSize" in request_dict:
            update_data["unit_size"] = request_dict["unitSize"]
        if "tierIds" in request_dict:
            await self._validate_tier_ids_exist(request_dict["tierIds"])
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
                    "description (or deprecated serviceDescription), "
                    "task/inferenceEndPoint (or deprecated taskType/"
                    "endpoint/hardwareDescription/api_key), "
                    "inferenceServerType, sslVerify, healthStatus, "
                    "benchmarks, expectedResponseSchema, isPublished, "
                    "isTryItDefault, policy, costPerUnit, unitSize, "
                    "tierIds. Note: name, modelId, modelVersion are not "
                    "updatable."
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
        self._cache.invalidate_service(instance.service_id)
        model = await self._models.get_by_id_version(
            instance.model_id, instance.model_version
        )
        if model is not None:
            tier_name_map = await self._services.get_tier_names_by_ids(instance.tier_ids or [])
            tier_names = [tier_name_map.get(tid) for tid in instance.tier_ids] if instance.tier_ids else None
            self._cache.set_service(
                instance.service_id, service_detail_dict(instance, model, tier_names=tier_names)
            )

    async def _load_endpoint_update_target(
        self, item: ServiceEndpointUpdateItem
    ) -> Tuple[Service, Any]:
        """Look up the target service and its model. DB access only — no
        live probe here, so callers can run this sequentially against the
        (non-concurrency-safe) AsyncSession and probe concurrently after."""
        instance = await self._services.get_by_service_id(item.serviceId)
        if instance is None:
            raise EntityNotFoundError(f"Service '{item.serviceId}'")

        model = await self._models.get_by_id_version(
            instance.model_id, instance.model_version
        )
        if model is None:
            raise EntityNotFoundError(
                f"Model '{instance.model_id}' v{instance.model_version}"
            )
        return instance, model

    async def _probe_endpoint_update_item(
        self, item: ServiceEndpointUpdateItem, instance: Service, model: Any
    ) -> None:
        """Live-validate one item's new endpoint. Raises
        EndpointValidationFailedError. Safe to run concurrently with other
        items since it makes no DB calls.

        ServiceEndpointUpdateItem only carries {serviceId, endpoint} — there
        is no per-item schema override in this bulk shape — so the shape
        check runs against whatever's already stored for that service (and
        falls back further to the task-type default inside
        _validate_endpoint_for_model if that's also unset), the same as a
        single-service endpoint-only update would.
        """
        await self._validate_endpoint_for_model(
            endpoint=item.endpoint,
            api_key=instance.api_key,
            model_inference_endpoint=model.inference_endpoint or {},
            task_type=(model.task or {}).get("type"),
            expected_response_schema=instance.expected_response_schema,
        )

    async def _commit_endpoint_updates(
        self,
        instances: List[Service],
        items: List[ServiceEndpointUpdateItem],
        *,
        updated_by: Optional[str],
    ) -> None:
        """Apply {endpoint, updated_by} to each instance and commit as one
        transaction, rolling back the whole batch on any failure."""
        try:
            for instance, item in zip(instances, items):
                update_data: Dict[str, Any] = {"endpoint": item.endpoint}
                if updated_by is not None:
                    update_data["updated_by"] = updated_by
                await self._services.apply_updates(instance, update_data)
            await self._services.commit()
        except Exception:
            await self._services.rollback()
            logger.exception("DB error bulk-updating service endpoints")
            raise

    async def _refresh_endpoint_cache(self, instance: Service, model: Any) -> None:
        self._cache.invalidate_service(instance.service_id)
        tier_name_map = await self._services.get_tier_names_by_ids(instance.tier_ids or [])
        tier_names = [tier_name_map.get(tid) for tid in instance.tier_ids] if instance.tier_ids else None
        self._cache.set_service(
            instance.service_id, service_detail_dict(instance, model, tier_names=tier_names)
        )

    @_log_rejections
    async def update_service_endpoints(
        self, items: List[ServiceEndpointUpdateItem], *, updated_by: Optional[str]
    ) -> List[str]:
        """Bulk-update only the `endpoint` field of multiple services in a
        single transaction (the array counterpart of update_service's
        endpoint-only PATCH). All items are validated before anything is
        written, and the whole batch commits or rolls back together.

        Targets are loaded sequentially (the AsyncSession isn't safe for
        concurrent use) but the live endpoint probes run concurrently via
        asyncio.gather, since each item's probe is a 15s-timeout network
        call and running them serially would let a large batch outlast a
        proxy timeout.
        """
        targets = [await self._load_endpoint_update_target(item) for item in items]
        await asyncio.gather(
            *(
                self._probe_endpoint_update_item(item, instance, model)
                for item, (instance, model) in zip(items, targets)
            )
        )
        instances = [instance for instance, _ in targets]
        await self._commit_endpoint_updates(instances, items, updated_by=updated_by)
        for instance, model in targets:
            await self._refresh_endpoint_cache(instance, model)
        return [instance.service_id for instance in instances]

    @_log_rejections
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

        self._cache.invalidate_service(instance.service_id)
        logger.info("Deleted service %s", instance.service_id)

    # ── Internals ──

    async def _validate_tier_ids_exist(self, tier_ids: Optional[List[str]]) -> None:
        """Raise if any of ``tier_ids`` doesn't reference a real PPU tier."""
        if not tier_ids:
            return
        found = await self._services.get_tier_names_by_ids(tier_ids)
        missing = [tid for tid in tier_ids if tid not in found]
        if missing:
            raise ValidationError(
                message=(
                    f"tierIds references nonexistent tier(s): {', '.join(missing)}."
                ),
                code="TIER_NOT_FOUND",
            )

    def _resolve_inference_schema(
        self,
        supplied: Optional[List[Dict[str, Any]]],
        model: Any,
        *,
        task_type: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Resolve the `inferenceEndPoint.schema` to persist for a new
        service.

        The caller's explicit value wins. Otherwise, derive one from the
        linked model's own `schema` — the request/response contract is a
        fact about the model artifact, not something that varies per
        deployment, so re-typing it at service-creation time is redundant
        whenever the model already declares one. Only raises if neither is
        available, or if the resolved value doesn't actually describe this
        service's own task type.
        """
        if supplied:
            schema = supplied
        else:
            model_schema = (model.inference_endpoint or {}).get("schema")
            if not model_schema:
                raise ValidationError(
                    message=(
                        "inferenceEndPoint.schema is required, and this "
                        "service's model has no schema on file to derive "
                        "it from — supply it manually."
                    ),
                    code="SCHEMA_REQUIRED",
                )
            schema = [model_schema]
            try:
                validate_inference_schema_entries(schema)
            except ValueError as exc:
                raise ValidationError(
                    message=(
                        f"inferenceEndPoint.schema could not be derived "
                        f"from this model's schema ({exc}) — supply it "
                        "manually."
                    ),
                    code="SCHEMA_REQUIRED",
                )

        if not schema_matches_task_type(task_type, schema):
            raise ValidationError(
                message=(
                    f"inferenceEndPoint.schema must include at least one "
                    f"entry whose taskType matches this service's task "
                    f"('{task_type}'); got: "
                    f"{[e.get('taskType') for e in schema]}"
                ),
                code="SCHEMA_TASK_TYPE_MISMATCH",
            )
        return schema

    def _validate_schema_task_type_consistency_on_update(
        self,
        *,
        new_task_type: Optional[str],
        new_schema: Optional[List[Dict[str, Any]]],
        existing_task_type: Optional[str],
        existing_schema: Optional[List[Dict[str, Any]]],
    ) -> None:
        """Catches the "only one side of the pair changed" case that
        ServiceUpdateRequest's own validator can't see — e.g. taskType is
        changed but schema isn't touched, so the OLD schema (for the OLD
        task type) would otherwise silently stick around on a service that
        now claims a different task.

        When BOTH are being changed together, ServiceUpdateRequest already
        validated the pair against each other — skip re-checking here to
        avoid a redundant, harder-to-word error at this layer. When
        NEITHER is being changed, also skip — this update doesn't touch
        either field, so there's nothing to validate; re-checking the
        existing stored pair against itself would risk rejecting an
        unrelated edit (e.g. `isPublished`) on a legacy row whose
        task/schema predate this consistency check.
        """
        task_type_changed = new_task_type is not None
        schema_changed = new_schema is not None
        if task_type_changed == schema_changed:
            return
        effective_task_type = new_task_type if task_type_changed else existing_task_type
        effective_schema = new_schema if schema_changed else existing_schema
        if not schema_matches_task_type(effective_task_type, effective_schema):
            raise ValidationError(
                message=(
                    f"inferenceEndPoint.schema must include at least one "
                    f"entry whose taskType matches this service's task "
                    f"('{effective_task_type}'); got: "
                    f"{[e.get('taskType') for e in (effective_schema or [])]}"
                ),
                code="SCHEMA_TASK_TYPE_MISMATCH",
            )

    async def _validate_endpoint_for_model(
        self,
        *,
        endpoint: str,
        api_key: Optional[str],
        model_inference_endpoint: Dict[str, Any],
        task_type: Optional[str],
        expected_response_schema: Optional[Dict[str, Any]],
    ) -> None:
        params = _extract_validation_params(model_inference_endpoint)
        safe_endpoint = sanitize_url_for_log(endpoint)
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
            expected_response_schema=expected_response_schema,
            is_sync_api=params["is_sync_api"],
            polling_url=params["polling_url"],
            poll_interval_ms=params["poll_interval_ms"],
            max_poll_attempts=settings.endpoint_validation_max_poll_attempts,
            max_poll_wait_seconds=settings.endpoint_validation_max_poll_wait_seconds,
            model_name=params["model_name"],
        )
        if not result.is_valid:
            failed_messages = [
                d.message for d in result.details if d.status == ValidationStatus.FAILED
            ]
            # The single line for a failed validation. Every failure surfaces
            # here and nowhere else, and this layer is the only one that has
            # the endpoint and task type together, so validate_endpoint stays
            # quiet on failure and reports only what passed.
            logger.warning(
                "Endpoint validation failed for %s (task=%s): %s",
                safe_endpoint,
                task_type,
                "; ".join(failed_messages),
            )
            raise EndpointValidationFailedError(
                message="Service endpoint validation failed.",
                errors=failed_messages,
            )

"""
Business-logic service for the Model domain.

Owns the rules:
- Model IDs are deterministic SHA256 hashes of (name, version).
- (name, version) must be unique.
- An ACTIVE version count limit per model name is enforced (configurable).
- Versions associated with at least one *published* service are immutable —
  cannot be updated or deleted.
- Updates to *deprecated* versions can be disabled via env flag.
- Model.name itself is not updatable (model_id depends on it).
- Cache is refreshed on writes and invalidated on deletes.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID


def _deep_merge(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge updates into existing JSONB data, preserving unset keys."""
    if not isinstance(existing, dict) or not isinstance(updates, dict):
        return updates
    merged = existing.copy()
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    EntityNotFoundError,
    ValidationError,
)
from app.models.model_management.model import Model, VersionStatus
from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.schemas.enums.model_management import VersionStatusEnum
from app.schemas.model_management.model import ModelCreateRequest, ModelUpdateRequest
from app.services.cache_service import CacheService
from .serializers import model_to_dict
from app.utils.hashing import generate_model_id

logger = logging.getLogger(__name__)


class ImmutableModelVersionError(AppError):
    """Raised when a model version cannot be modified because it backs a
    published service. Surfaces as HTTP 409."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="IMMUTABLE_MODEL_VERSION", status_code=409
        )


class DuplicateModelVersionError(AppError):
    """Raised when (name, version) already exists. HTTP 409."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="DUPLICATE_MODEL_VERSION", status_code=409
        )


class ModelService:
    """Application-level service orchestrating model use-cases."""

    def __init__(
        self,
        model_repo: ModelRepository,
        service_repo: ServiceRepository,
        cache: CacheService,
    ) -> None:
        self._models = model_repo
        self._services = service_repo
        self._cache = cache

    # ── Reads ──

    async def get_model(
        self, model_id: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return a single model, preferring cached value when present."""
        cached = await self._cache.get_model(model_id, version)
        if cached:
            return cached

        instance: Optional[Model] = None
        if version:
            instance = await self._models.get_by_id_version(model_id, version)
        else:
            instance = await self._models.get_default_version(model_id)
        if instance is None:
            # Fallback: caller may pass an internal UUID
            try:
                instance = await self._models.get_by_uuid(UUID(model_id))
            except (ValueError, TypeError):
                instance = None

        if instance is None:
            raise EntityNotFoundError(f"Model '{model_id}'")

        data = model_to_dict(instance)
        await self._cache.set_model(
            instance.model_id,
            instance.version,
            data,
            is_default_version=(instance.version_status == VersionStatus.ACTIVE
                                and version is None),
        )
        return data

    async def list_models(
        self,
        *,
        task_types: Optional[List[str]] = None,
        include_deprecated: bool = True,
        version_status: Optional[str] = None,
        model_name: Optional[str] = None,
        created_by: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        rows = await self._models.list_models(
            task_types=task_types,
            include_deprecated=include_deprecated,
            version_status=version_status,
            model_name=model_name,
            created_by=created_by,
            offset=offset,
            limit=limit,
        )
        items = [model_to_dict(m) for m in rows]
        if offset > 0 or limit is not None:
            total = await self._models.count_models(
                task_types=task_types,
                version_status=version_status,
                model_name=model_name,
                created_by=created_by,
            )
        else:
            total = len(items)
        return items, total

    # ── Writes ──

    async def create_model(
        self, payload: ModelCreateRequest, *, created_by: Optional[str]
    ) -> str:
        """Persist a new model version and return its generated model_id."""
        # Duplicate check on (name, version)
        existing = await self._models.get_by_name_version(payload.name, payload.version)
        if existing is not None:
            raise DuplicateModelVersionError(
                f"Model with name '{payload.name}' and version "
                f"'{payload.version}' already exists.",
            )

        version_status = (
            VersionStatus(payload.versionStatus.value)
            if payload.versionStatus
            else VersionStatus.ACTIVE
        )

        # Active-version cap
        if version_status == VersionStatus.ACTIVE:
            active_count = await self._models.count_active_versions(payload.name)
            limit = settings.max_active_versions_per_model
            if active_count >= limit:
                raise ValidationError(
                    f"Maximum number of active versions ({limit}) reached for "
                    f"model '{payload.name}'. Please deprecate an existing "
                    "active version before creating a new one.",
                    code="MAX_ACTIVE_VERSIONS_EXCEEDED",
                )

        encoded = jsonable_encoder(payload)
        model_id = generate_model_id(payload.name, payload.version)

        inference_endpoint: Dict[str, Any] = {}
        for _ep_key in ("adapterConfig", "schema", "callbackUrl", "inferenceApiKey", "isSyncApi", "asyncApiDetails"):
            if encoded.get(_ep_key) is not None:
                inference_endpoint[_ep_key] = encoded[_ep_key]

        instance = Model(
            model_id=model_id,
            version=encoded["version"],
            version_status=version_status,
            name=encoded["name"],
            description=encoded["description"],
            ref_url=encoded["refUrl"],
            task=encoded.get("task") or {},
            languages=encoded.get("languages") or [],
            is_lang_detection_enabled=encoded.get("isLangDetectionEnabled") or False,
            is_multilingual=encoded.get("isMultilingual") or False,
            license=encoded.get("license"),
            license_url=encoded.get("licenseUrl"),
            domain=encoded.get("domain") or [],
            inference_endpoint=inference_endpoint,
            benchmarks=encoded.get("benchmarks") or [],
            submitter=encoded.get("submitter") or {},
            training_dataset=encoded.get("trainingDataset") or {},
            class_instance=encoded.get("classInstance"),
            created_by=created_by,
        )
        try:
            await self._models.add(instance)
            await self._models.commit()
            await self._models.refresh(instance)
        except Exception:
            await self._models.rollback()
            logger.exception("DB error creating model")
            raise

        # Warm the cache (best-effort)
        data = model_to_dict(instance)
        await self._cache.set_model(
            instance.model_id, instance.version, data,
            is_default_version=(version_status == VersionStatus.ACTIVE),
        )
        logger.info("Created model '%s' v%s (id=%s)", payload.name, payload.version, model_id)
        return model_id

    async def update_model(
        self, payload: ModelUpdateRequest, *, updated_by: Optional[str]
    ) -> None:
        """Apply a PATCH to an existing (model_id, version)."""
        if not payload.version:
            raise ValidationError(
                "Version is required to update a specific model version.",
                code="VERSION_REQUIRED",
            )

        instance = await self._models.get_by_id_version(payload.modelId, payload.version)
        if instance is None:
            existing_model = await self._models.get_by_model_id(payload.modelId)
            if existing_model is not None:
                conflict = await self._models.get_by_name_version(
                    existing_model.name, payload.version
                )
                if conflict is not None:
                    raise DuplicateModelVersionError(
                        f"Model with name '{existing_model.name}' and version "
                        f"'{payload.version}' already exists.",
                    )
            raise EntityNotFoundError(
                f"Model '{payload.modelId}' v{payload.version}"
            )

        # Immutability: published services lock down their model version
        published_service_ids = await self._services.list_published_for_model_version(
            payload.modelId, payload.version
        )
        if published_service_ids:
            raise ImmutableModelVersionError(
                f"Model version '{payload.modelId}' v{payload.version} cannot "
                f"be modified because it is associated with "
                f"{len(published_service_ids)} published service(s): "
                f"{', '.join(published_service_ids)}. Unpublish the service(s) "
                "first to modify this model version.",
            )

        # Deprecated-update gating
        if (
            instance.version_status == VersionStatus.DEPRECATED
            and not settings.allow_deprecated_model_changes
        ):
            raise ValidationError(
                f"Model version '{payload.modelId}' v{payload.version} cannot "
                "be modified because it is deprecated.",
                code="DEPRECATED_MODEL_UPDATE_NOT_ALLOWED",
            )

        # PATCH semantics
        request_dict = payload.model_dump(exclude_unset=True)
        update_data: Dict[str, Any] = {}
        ep_field_updates: Dict[str, Any] = {}

        if payload.versionStatus is not None:
            new_status = VersionStatus(payload.versionStatus.value)
            # If activating, enforce the max-active cap (excluding this version)
            if (
                new_status == VersionStatus.ACTIVE
                and instance.version_status != VersionStatus.ACTIVE
            ):
                active_count = await self._models.count_active_versions(
                    instance.name, exclude_version=instance.version
                )
                limit = settings.max_active_versions_per_model
                if active_count >= limit:
                    raise ValidationError(
                        f"Maximum number of active versions ({limit}) reached "
                        f"for model {payload.modelId}. Please deprecate an "
                        "existing active version before activating this one.",
                        code="MAX_ACTIVE_VERSIONS_EXCEEDED",
                    )
            update_data["version_status"] = new_status

        for key, value in request_dict.items():
            if key in ("modelId", "version", "versionStatus", "submittedOn", "updatedOn"):
                continue
            if key == "name":
                raise ValidationError(
                    "Model name cannot be updated. Model ID is derived from "
                    "(name, version). Create a new model version instead.",
                    code="NAME_NOT_UPDATABLE",
                )
            if value is None:
                continue
            if key == "refUrl":
                update_data["ref_url"] = value
            elif key == "adapterConfig":
                ep_field_updates["adapterConfig"] = jsonable_encoder(value)
            elif key == "endpoint_schema":
                ep_field_updates["schema"] = jsonable_encoder(value)
            elif key in ("callbackUrl", "inferenceApiKey", "isSyncApi", "asyncApiDetails"):
                ep_field_updates[key] = jsonable_encoder(value)
            elif key in ("task", "languages", "domain", "benchmarks", "submitter", "trainingDataset"):
                target_key = "training_dataset" if key == "trainingDataset" else key
                update_data[target_key] = jsonable_encoder(value)
            elif key == "classInstance":
                update_data["class_instance"] = value
            elif key == "isLangDetectionEnabled":
                update_data["is_lang_detection_enabled"] = value
            elif key == "isMultilingual":
                update_data["is_multilingual"] = value
            elif key == "licenseUrl":
                update_data["license_url"] = value
            else:
                update_data[key] = value

        if ep_field_updates:
            existing_ep = dict(instance.inference_endpoint or {})
            if "adapterConfig" in ep_field_updates:
                existing_adapter = (
                    existing_ep.get("adapterConfig")
                    or existing_ep.get("adapter_config")
                    or {}
                )
                existing_ep["adapterConfig"] = _deep_merge(existing_adapter, ep_field_updates["adapterConfig"])
                existing_ep.pop("adapter_config", None)
            if "schema" in ep_field_updates:
                existing_ep["schema"] = ep_field_updates["schema"]
            for _direct_key in ("callbackUrl", "inferenceApiKey", "isSyncApi", "asyncApiDetails"):
                if _direct_key in ep_field_updates:
                    existing_ep[_direct_key] = ep_field_updates[_direct_key]
            update_data["inference_endpoint"] = existing_ep

        if updated_by is not None:
            update_data["updated_by"] = updated_by

        if not update_data:
            return

        try:
            await self._models.apply_updates(instance, update_data)
            await self._models.commit()
            await self._models.refresh(instance)
        except Exception:
            await self._models.rollback()
            logger.exception("DB error updating model")
            raise

        # Refresh cache
        await self._cache.invalidate_all_versions(instance.model_id)
        await self._cache.set_model(
            instance.model_id, instance.version, model_to_dict(instance),
            is_default_version=(instance.version_status == VersionStatus.ACTIVE),
        )
        logger.info("Updated model %s v%s", instance.model_id, instance.version)

    async def delete_model(self, id_str: str) -> None:
        """Delete a model version by its model_id.

        Hard rules:
        - 404 if no row matches the model_id.
        - 409 if any *published* service references this (model_id, version).
        - Cascading delete of unpublished services associated with the
          version (their cache entries are wiped too).
        """
        instance = await self._models.get_by_model_id(id_str)
        if instance is None:
            raise EntityNotFoundError(f"Model '{id_str}'")

        published = await self._services.list_published_for_model_version(
            instance.model_id, instance.version
        )
        if published:
            raise ImmutableModelVersionError(
                f"Model version '{instance.model_id}' v{instance.version} "
                "cannot be deleted because it is associated with "
                f"{len(published)} published service(s): {', '.join(published)}. "
                "Unpublish the service(s) first to delete this model version.",
            )

        # Cascade delete unpublished services + invalidate their cache
        unpublished = await self._services.list_unpublished_for_model_version(
            instance.model_id, instance.version
        )
        for svc in unpublished:
            self._cache.invalidate_service(svc.service_id)
        if unpublished:
            await self._services.delete_unpublished_for_model_version(
                instance.model_id, instance.version
            )

        try:
            await self._models.delete_by_model_id(instance.model_id)
            await self._models.commit()
        except Exception:
            await self._models.rollback()
            logger.exception("DB error deleting model")
            raise

        await self._cache.invalidate_all_versions(instance.model_id)
        logger.info("Deleted model %s v%s", instance.model_id, instance.version)

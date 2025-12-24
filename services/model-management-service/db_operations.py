from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select , delete , update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import Dict, Any, List, Optional

from models.db_models import Model , Service
from models.cache_models_services import ModelCache , ServiceCache
from models.model_create import ModelCreateRequest
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_view import ServiceViewResponse
from models.service_list import ServiceListResponse
from models.service_health import ServiceHeartbeatRequest
from models.type_enum import TaskTypeEnum

from db_connection import AppDatabase
from uuid import UUID
from logger import logger
import json
import time
from datetime import datetime



def _json_safe(value: Any) -> Any:
    """
    Safely encode a value to JSON-serializable format.
    
    Args:
        value: Any value to encode
        
    Returns:
        JSON-serializable representation of the value
    """
    try:
        return jsonable_encoder(value)
    except Exception:
        return json.loads(json.dumps(value))
    


####################################################### Model Functions #######################################################

def model_redis_safe_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert payload dictionary to Redis-safe format.
    Mutates the input dictionary in place and returns it.
    Preserves existing string values and only converts lists/dicts.
    
    Args:
        payload_dict: Dictionary containing model data with nested structures
        
    Returns:
        Modified dictionary with Redis-safe string representations
    """
    # Modify payload_dict to make all cache fields Redis-safe
    task = payload_dict.get("task")
    if task and isinstance(task, dict):
        payload_dict["task_type"] = task.get("type", "")

    # Convert lists → comma-separated (preserve existing strings)
    domain = payload_dict.get("domain")
    if domain and isinstance(domain, list):
        payload_dict["domain"] = ",".join(str(item) for item in domain)

    # Convert languages list → comma-separated sourceLanguage values (preserve existing strings)
    languages = payload_dict.get("languages")
    if languages and isinstance(languages, list):
        payload_dict["languages"] = ",".join(
            str(lang.get("sourceLanguage", "")) if isinstance(lang, dict) else str(lang)
            for lang in languages
        )

    # Convert complex lists → JSON string (preserve existing strings)
    benchmarks = payload_dict.get("benchmarks")
    if benchmarks:
        if isinstance(benchmarks, str):
            pass
        else:
            # Try to convert to JSON string
            try:
                payload_dict["benchmarks"] = json.dumps(benchmarks)
            except (TypeError, ValueError):
                payload_dict["benchmarks"] = ""

    return payload_dict
    

async def save_model_to_db(payload: ModelCreateRequest):
    """
    Save a new model entry to the database.
    Includes:
      - Duplicate (model_id, version) check
      - Record creation
      - Commit / rollback

    """
    db: AsyncSession = AppDatabase()
    try:
        # Pre-check for duplicate (model_id, version) combination
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        
        if await repo.check_version_exists(payload.modelId, payload.version):
            logger.warning(f"Duplicate model_id and version: {payload.modelId} v{payload.version}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model with ID {payload.modelId} version {payload.version} already exists."
            )
        
        payload_dict = _json_safe(payload)

        now_epoch = int(time.time())

        payload_dict["submittedOn"] = now_epoch
        payload_dict["updatedOn"] = now_epoch

        # Create new model record
        new_model = Model(
            model_id=payload_dict.get("modelId"),
            version=payload_dict.get("version"),
            submitted_on=payload_dict.get("submittedOn"),
            updated_on=payload_dict.get("updatedOn"),
            name=payload_dict.get("name"),
            description=payload_dict.get("description"),
            ref_url=payload_dict.get("refUrl"),
            task=payload_dict.get("task",{}),
            languages=payload_dict.get("languages",[]),
            license=payload_dict.get("license"),
            domain=payload_dict.get("domain",[]),
            inference_endpoint=payload_dict.get("inferenceEndPoint",{}),
            benchmarks=payload_dict.get("benchmarks",[]),
            submitter=payload_dict.get("submitter",{}),
            version_status=payload_dict.get("versionStatus", "active"),
            release_notes=payload_dict.get("releaseNotes"),
            is_immutable=False,
        )

        db.add(new_model)
        await db.commit()
        await db.refresh(new_model)
        logger.info(f"Model {payload.modelId} successfully saved to DB.")

        # Cache the model in Redis with version-specific key
        try:
            payload_dict = model_redis_safe_payload(payload_dict)
            # Update cache key to include version: modelId becomes composite key
            cache_key = f"{payload_dict.get('modelId')}:{payload_dict.get('version')}"
            payload_dict['modelId'] = cache_key  # Use composite key for caching
            cache_entry = ModelCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Model {new_model.model_id} v{new_model.version} cached in Redis.")
        except Exception as ce:
            logger.warning(f"Could not cache model {new_model.model_id} v{new_model.version}: {ce}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Error while saving model to DB.")
        raise Exception("Insert failed due to internal DB error") from e
    finally:
        await db.close()
    


async def update_by_filter(filters: Dict[str, Any], data: Dict[str, Any]) -> int:
    """
    Update model records based on provided filters.
    """
    
    db: AsyncSession = AppDatabase()
    try:
        query = select(Model)

        if not filters:
            raise ValueError("Filters required to update records.")

        # Apply filters
        for key, value in filters.items():
            if hasattr(Model, key):
                query = query.where(getattr(Model, key) == value)
            else:
                raise ValueError(f"Invalid filter field: {key}")

        result = await db.execute(query)
        records = result.scalars().all()

        if not records:
            return 0

        json_fields = {
            "task",
            "languages",
            "domain",
            "inference_endpoint",
            "benchmarks",
            "submitter",
        }

        for record in records:
            for field, value in data.items():
                setattr(record, field, value)

                # MUST DO THIS for JSONB fields
                if field in json_fields:
                    flag_modified(record, field)

        await db.commit()
        return len(records)

    except Exception as e:
        await db.rollback()
        logger.exception("Failed to update records.")
        raise ValueError(f"Failed to update records: {e}") from e
    finally:
        await db.close()


async def update_model(payload: ModelUpdateRequest):
    """
    Update model record in PostgreSQL and refresh Redis cache.
    Note: modelId and version are used as identifier and are NOT changed during update.
    Checks is_immutable flag before allowing updates.
        """

    logger.info(f"Attempting to update model: {payload.modelId} version: {payload.version}")

    # Check if version is specified (required for multi-version support)
    if not payload.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Version is required to update a model. Specify which version to update."
        )
    
    # Check immutability
    from repositories.model_repository import ModelRepository
    db: AsyncSession = AppDatabase()
    try:
        repo = ModelRepository(db)
        model = await repo.find_by_model_id_and_version(payload.modelId, payload.version)
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {payload.modelId} version {payload.version} not found"
            )
        if model.is_immutable:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Model {payload.modelId} version {payload.version} is immutable and cannot be modified"
            )
    finally:
        await db.close()

    request_dict = payload.model_dump(exclude_none=True)
    now_epoch = int(time.time())

    # 1. Update DB first
    postgres_data = {}

    for key, value in request_dict.items():
        if value is None:
            continue    # PATCH: skip null fields

        # Skip modelId (used only for filtering, not updated)
        if key == "modelId":
            continue

        # Custom snake_case mapping
        if key == "refUrl":
            postgres_data["ref_url"] = value
        elif key == "inferenceEndPoint":
            postgres_data["inference_endpoint"] = _json_safe(value)
        elif key in ("task", "languages", "domain", "benchmarks", "submitter"):
            postgres_data[key] = _json_safe(value)
        else:
            postgres_data[key] = value

    postgres_data["updated_on"] = now_epoch
    logger.info(f"Updating DB for model {payload.modelId} with fields: {list(postgres_data.keys())}")
    logger.debug(f"DB update data: {postgres_data}")

    # 2. Repository update - filter by both model_id and version
    result = await update_by_filter({"model_id": payload.modelId, "version": payload.version}, postgres_data)

    # 3. Update Redis cache
    # Try to get existing cache, or fetch from DB if cache doesn't exist
    cache_key = f"{payload.modelId}:{payload.version}" if payload.version else payload.modelId
    try:
        cache = ModelCache.get(cache_key)
        # Cache exists, patch it
        new_cache = cache.model_dump()
        model_fields = cache.__class__.model_fields

        for key, value in request_dict.items():
            if key in model_fields and value is not None:
                new_cache[key] = value

        new_cache["updatedOn"] = now_epoch
    except Exception:
        # Cache doesn't exist, fetch from DB and create cache entry
        logger.info(f"Model {payload.modelId} version {payload.version} not found in cache, fetching from DB to create cache entry")
        db: AsyncSession = AppDatabase()
        try:
            from repositories.model_repository import ModelRepository
            repo = ModelRepository(db)
            db_model = await repo.find_by_model_id_and_version(payload.modelId, payload.version)
            
            if not db_model:
                logger.warning(f"Model {payload.modelId} not found in DB")
                return result
            
            # Convert DB model to cache format
            new_cache = _json_safe({
                "modelId": db_model.model_id,
                "version": db_model.version,
                "submittedOn": db_model.submitted_on,
                "updatedOn": db_model.updated_on,
                "name": db_model.name,
                "description": db_model.description,
                "refUrl": db_model.ref_url,
                "task": db_model.task,
                "languages": db_model.languages,
                "license": db_model.license,
                "domain": db_model.domain,
                "inferenceEndPoint": db_model.inference_endpoint,
                "benchmarks": db_model.benchmarks,
                "submitter": db_model.submitter,
                "versionStatus": db_model.version_status,
                "releaseNotes": db_model.release_notes,
            })
            
            # Apply updates to the fetched data
            for key, value in request_dict.items():
                if key != "modelId" and value is not None:
                    # Map camelCase to snake_case for DB fields
                    if key == "refUrl":
                        new_cache["refUrl"] = value
                    elif key == "inferenceEndPoint":
                        new_cache["inferenceEndPoint"] = value
                    else:
                        new_cache[key] = value
            
            new_cache["updatedOn"] = now_epoch
        except Exception as e:
            logger.exception(f"Error fetching model from DB for cache: {e}")
            return result

    # Convert to Redis-safe format and save
    try:
        new_cache = model_redis_safe_payload(new_cache)
        # Update cache key to include version
        cache_key = f"{payload.modelId}:{payload.version}" if payload.version else payload.modelId
        new_cache['modelId'] = cache_key  # Use composite key for caching
        updated_cache = ModelCache(**new_cache)
        updated_cache.save()
        logger.info(f"Cache updated for model {payload.modelId} v{payload.version}")
    except Exception as ce:
        logger.warning(f"Failed to update cache for {payload.modelId} v{payload.version}: {ce}")

    logger.info(f"Model {payload.modelId} successfully updated.")

    return result





async def delete_model_by_uuid(id_str: str) -> int:
    """Delete model by internal UUID (id)"""

    db: AsyncSession = AppDatabase()

    try:

        # Convert to UUID
        try:
            uuid = UUID(id_str)
        except ValueError:
            logger.warning(f"Invalid UUID provided for delete: {id_str}")
            return 0

        result = await db.execute(select(Model).filter(Model.id == uuid))
        model = result.scalars().first()

        if not model:
            logger.warning(f"Model with UUID {uuid} not found for delete.")
            return 0

        model_id = model.model_id

        # ---- Delete from Cache ----
        # Delete all versions of this model from cache
        try:
            from repositories.model_repository import ModelRepository
            repo = ModelRepository(db)
            all_versions = await repo.find_all_versions(model_id)
            for version_model in all_versions:
                cache_key = f"{model_id}:{version_model.version}"
                try:
                    cache_entry = ModelCache.get(cache_key)
                    if cache_entry:
                        ModelCache.delete(cache_key)
                        logger.info(f"Cache deleted for modelId='{model_id}' version='{version_model.version}'")
                except Exception:
                    pass  # Cache entry might not exist

        except Exception as cache_err:
            logger.warning(f"ModelCache delete failed for {uuid}: {cache_err}")


        await db.execute(delete(Model).where(Model.id == uuid))

        await db.commit()
        logger.info(f"DB: Model with ID {uuid} deleted successfully.")

        return 1
    except Exception as e:
        await db.rollback()
        logger.exception("Error deleting model from DB.")
        raise Exception("Delete failed due to internal DB error") from e
    finally:
        await db.close()



async def get_model_details(model_id: str, version: Optional[str] = None) -> Dict[str, Any]:
    """
    Get model details by model_id and optionally version.
    If version is not specified, returns the latest active version.
    """
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        
        if version:
            model = await repo.find_by_model_id_and_version(model_id, version)
        else:
            # Get latest active version
            model = await repo.get_latest_active_version(model_id)
            if not model:
                # Fallback to any version if no active version exists
                model = await repo.find_by_model_id(model_id)

        if not model:
            # Fallback: try UUID
            try:
                uuid = UUID(model_id)
                model_result = await db.execute(select(Model).where(Model.id == uuid))
                model = model_result.scalars().first()
            except Exception:
                pass

        if not model:
            return None
        
        # Get all versions for this model
        all_versions = await repo.find_all_versions(model_id)
        version_list = [v.version for v in all_versions]

        return {
            "modelId": model.model_id,
            "uuid": str(model.id),
            "version": model.version,
            "name": model.name,
            "description": model.description,
            "languages": model.languages or [],
            "domain": model.domain,
            "submitter": model.submitter,
            "license": model.license,
            "inferenceEndPoint": model.inference_endpoint,
            "source": model.ref_url or "",  ## ask value for this field
            "task": model.task,
            "isPublished": model.is_published,
            "publishedAt": datetime.fromtimestamp(model.published_at).isoformat() if model.published_at else None,
            "unpublishedAt": datetime.fromtimestamp(model.unpublished_at).isoformat() if model.unpublished_at else None,
            "versionStatus": model.version_status,
            "releaseNotes": model.release_notes,
            "isImmutable": model.is_immutable,
            "allVersions": version_list,
         }
     
    except Exception as e:
         logger.error(f"[DB] Error fetching model details: {str(e)}")
         raise
    finally:
         await db.close()
    

async def list_all_models(task_type: TaskTypeEnum | None, version_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch all model records from DB and convert to response format."""

    db: AsyncSession = AppDatabase()
    try:
        query = select(Model)
        if task_type:
            query = query.where(Model.task['type'].astext == task_type.value)
        if version_status:
            query = query.where(Model.version_status == version_status)

        result = await db.execute(query)
        models = result.scalars().all()

        if not models:
            logger.info(f"[DB] No models found for type :{task_type}, version_status: {version_status}")
            return None

        result = []
        for item in models:
            # Convert SQLAlchemy model → dict
            data = item.__dict__.copy()
            data.pop("_sa_instance_state", None)

            # Build response object
            result.append({
                "modelId": str(data.get("model_id")),
                "uuid": str(data.get("id")),
                "version": str(data.get("version")),
                "name": data.get("name"),
                "description": data.get("description"),
                "languages": data.get("languages") or [],
                "domain": data.get("domain"),
                "submitter": data.get("submitter"),
                "license": data.get("license"),
                "inferenceEndPoint": data.get("inference_endpoint"),
                "source": data.get("ref_url"),
                "task": data.get("task", {}),
                "isPublished": data.get("is_published", {}),
                "publishedAt": datetime.fromtimestamp(data.get("published_at", None)).isoformat() if data.get("published_at", None) else None ,
                "unpublishedAt": datetime.fromtimestamp( data.get("unpublished_at", None)).isoformat() if  data.get("unpublished_at", None) else None,
                "versionStatus": data.get("version_status", "active"),
                "releaseNotes": data.get("release_notes"),
                "isImmutable": data.get("is_immutable", False),
            })

        return result
    except Exception as e:
        logger.error(f"[DB] Error fetching model list: {str(e)}")
        raise
    finally:
        await db.close()


async def publish_model(payload_modelId: str, version: Optional[str] = None):
    """
    Publish a model by setting is_published to True and updating published_at timestamp.
    If version is provided, publishes that specific version. Otherwise publishes latest active version.
    Sets is_immutable=True when publishing if ENABLE_VERSION_IMMUTABILITY is enabled.
    """
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        from config import settings
        repo = ModelRepository(db)
        
        if version:
            model = await repo.find_by_model_id_and_version(payload_modelId, version)
        else:
            model = await repo.get_latest_active_version(payload_modelId)

        if not model:
            logger.warning(f"Model with ID {payload_modelId} version {version} not found for publish.")
            return 0

        now_epoch = int(time.time())
        
        update_values = {
            "is_published": True,
            "published_at": now_epoch,
            "unpublished_at": None
        }
        
        # Set immutability if enabled
        if settings.ENABLE_VERSION_IMMUTABILITY:
            update_values["is_immutable"] = True

        await db.execute(
                update(Model)
                .where(Model.model_id == payload_modelId, Model.version == model.version)
                .values(**update_values)
            )

        await db.commit()
        logger.info(f"Model {payload_modelId} version {model.version} published successfully.")
        
        # Mark as immutable in repository if needed
        if settings.ENABLE_VERSION_IMMUTABILITY:
            await repo.mark_version_as_immutable(payload_modelId, model.version)

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while publishing model.")
        raise Exception("Publish failed due to internal DB error") from e
    finally:
        await db.close()
    
async def unpublish_model(payload_modelId: str, version: Optional[str] = None):
    """
    Unpublish a model by setting is_published to False and updating unpublished_at timestamp.
    If version is provided, unpublishes that specific version. Otherwise unpublishes latest active version.
    """
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        
        if version:
            model = await repo.find_by_model_id_and_version(payload_modelId, version)
        else:
            model = await repo.get_latest_active_version(payload_modelId)

        if not model:
            logger.warning(f"Model with ID {payload_modelId} version {version} not found for unpublish.")
            return 0

        now_epoch = int(time.time())

        await db.execute(
                update(Model)
                .where(Model.model_id == payload_modelId, Model.version == model.version)
                .values(
                    is_published=False,
                    unpublished_at=now_epoch
                )
            )

        await db.commit()
        logger.info(f"Model {payload_modelId} version {model.version} unpublished successfully.")

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while unpublishing model.")
        raise Exception("Unpublish failed due to internal DB error") from e
    finally:
        await db.close()


async def create_model_version(model_id: str, payload, base_model_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new version under an existing model.
    Uses base_model_data as template and updates with version-specific fields.
    """
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        from services.version_service import VersionService
        from config import settings
        
        repo = ModelRepository(db)
        version_service = VersionService(db)
        
        # Validate version creation
        await version_service.validate_version_creation(model_id, payload.version)
        
        # Check active version limit and auto-deprecate if needed
        active_count = await repo.count_active_versions(model_id)
        if active_count >= settings.MAX_ACTIVE_VERSIONS_PER_MODEL:
            await version_service.enforce_active_version_limit(model_id)
        
        # Prepare new version data based on base model
        now_epoch = int(time.time())
        
        new_model = Model(
            model_id=model_id,
            version=payload.version,
            submitted_on=base_model_data.get("submitted_on", now_epoch),
            updated_on=now_epoch,
            name=base_model_data.get("name", ""),
            description=base_model_data.get("description"),
            ref_url=base_model_data.get("ref_url"),
            task=base_model_data.get("task", {}),
            languages=base_model_data.get("languages", []),
            license=base_model_data.get("license"),
            domain=base_model_data.get("domain", []),
            inference_endpoint=base_model_data.get("inference_endpoint", {}),
            benchmarks=base_model_data.get("benchmarks", []),
            submitter=base_model_data.get("submitter", {}),
            version_status=getattr(payload, "versionStatus", settings.DEFAULT_VERSION_STATUS),
            release_notes=getattr(payload, "releaseNotes", None),
            is_immutable=False,
        )
        
        db.add(new_model)
        await db.commit()
        await db.refresh(new_model)
        logger.info(f"Model version {model_id} v{payload.version} created successfully.")
        
        return {
            "modelId": new_model.model_id,
            "version": new_model.version,
            "versionStatus": new_model.version_status,
            "releaseNotes": new_model.release_notes,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Error while creating model version.")
        raise Exception("Model version creation failed") from e
    finally:
        await db.close()


async def get_model_versions(model_id: str) -> List[Dict[str, Any]]:
    """List all versions of a model."""
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        
        versions = await repo.find_all_versions(model_id)
        
        return [
            {
                "version": v.version,
                "versionStatus": v.version_status,
                "releaseNotes": v.release_notes,
                "isPublished": v.is_published,
                "isImmutable": v.is_immutable,
                "publishedAt": datetime.fromtimestamp(v.published_at).isoformat() if v.published_at else None,
                "createdAt": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
    except Exception as e:
        logger.exception(f"Error fetching versions for model {model_id}")
        raise
    finally:
        await db.close()


async def deprecate_model_version(model_id: str, version: str) -> bool:
    """Mark a model version as deprecated."""
    db: AsyncSession = AppDatabase()
    try:
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        
        result = await repo.mark_version_as_deprecated(model_id, version)
        logger.info(f"Model {model_id} version {version} deprecated successfully.")
        return result
    except Exception as e:
        logger.exception(f"Error deprecating model version {model_id} v{version}")
        raise
    finally:
        await db.close()


async def get_services_by_model_version(model_id: str, version: str) -> List[Dict[str, Any]]:
    """Find all services using a specific model version."""
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Service).where(
            Service.model_id == model_id,
            Service.model_version == version
        )
        result = await db.execute(stmt)
        services = result.scalars().all()
        
        return [
            {
                "serviceId": s.service_id,
                "name": s.name,
                "endpoint": s.endpoint,
            }
            for s in services
        ]
    except Exception as e:
        logger.exception(f"Error fetching services for model {model_id} version {version}")
        raise
    finally:
        await db.close()


async def get_services_using_deprecated_versions(model_id: str) -> List[Dict[str, Any]]:
    """Identify services still using deprecated versions of a model."""
    from services.service_version_service import ServiceVersionService
    db: AsyncSession = AppDatabase()
    try:
        service_version_service = ServiceVersionService(db)
        return await service_version_service.get_services_using_deprecated_versions(model_id)
    except Exception as e:
        logger.exception(f"Error fetching services using deprecated versions for model {model_id}")
        raise
    finally:
        await db.close()

####################################################### Service Functions #######################################################


async def save_service_to_db(payload: ServiceCreateRequest):
    """
    Save a new service entry to the database.
    """
    db: AsyncSession = AppDatabase()
    try:
        # Pre-check for duplicates service id
        result = await db.execute(select(Service).where(Service.service_id == payload.serviceId))
        existing = result.scalars().first()
        if existing:
            logger.warning(f"Duplicate service_id: {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service with ID {payload.serviceId} already exists."
            )
        
        # Check if associated model version exists
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        model_exists = await repo.find_by_model_id_and_version(payload.modelId, payload.modelVersion)
        if not model_exists:
            raise HTTPException(
                status_code=400,
                detail=f"Model with ID {payload.modelId} version {payload.modelVersion} does not exist, cannot create service."
            )
        
        # Check if model version is deprecated (warn or prevent based on config)
        from config import settings
        if model_exists.version_status == "deprecated" and settings.WARN_ON_DEPRECATED_VERSION_USAGE:
            logger.warning(f"Service {payload.serviceId} is being created with deprecated model version {payload.modelId} v{payload.modelVersion}")
            if not settings.ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model version {payload.modelId} v{payload.modelVersion} is deprecated and cannot be used for services."
                )
        
        payload_dict = _json_safe(payload.model_dump(by_alias=True))

        now_epoch = int(time.time())
        payload_dict["publishedOn"] = now_epoch

        # Create new service record
        new_service = Service(
            service_id=payload_dict.get("serviceId"),
            name=payload_dict.get("name"),
            service_description=payload_dict.get("serviceDescription"),
            hardware_description=payload_dict.get("hardwareDescription"),
            published_on=payload_dict.get("publishedOn"),
            model_id=payload_dict.get("modelId"),
            model_version=payload_dict.get("modelVersion"),
            endpoint=payload_dict.get("endpoint"),
            api_key=payload_dict.get("apiKey"),
            health_status=payload_dict.get("healthStatus", {}),
            benchmarks=payload_dict.get("benchmarks", []),
            version_updated_at=now_epoch,
        )
        db.add(new_service)
        await db.commit()
        await db.refresh(new_service)
        logger.info(f"Service {payload.serviceId} successfully saved to DB.")


        # Cache the service in Redis
        try:
            cache_entry = ServiceCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Service {new_service.service_id} cached in Redis with model version {payload.modelVersion}.")
        except Exception as ce:
            logger.warning(f"Could not cache service {new_service.service_id}: {ce}")


    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error while saving service to DB.")
        raise Exception("Insert failed due to internal DB error") from e
    finally:
        await db.close()


async def update_service(request: ServiceUpdateRequest):
    """
    Update an existing service record in PostgreSQL and refresh Redis cache.
    Note: serviceId is used as identifier and is NOT changed during update.
    """

    db: AsyncSession = AppDatabase()

    try:
        if not request.serviceId:
            logger.warning("Missing serviceId in update request")
            return 0

        request_dict = request.model_dump(exclude_none=True,by_alias=True)

        # 1. Build DB update dict
        db_update = {}

        if "name" in request_dict:
            db_update["name"] = request_dict["name"]
        if "serviceDescription" in request_dict:
            db_update["service_description"] = request_dict["serviceDescription"]
        if "hardwareDescription" in request_dict:
            db_update["hardware_description"] = request_dict["hardwareDescription"]
        if "endpoint" in request_dict:
            db_update["endpoint"] = request_dict["endpoint"]
        if "api_key" in request_dict:
            db_update["api_key"] = request_dict["api_key"]
        if "modelId" in request_dict:
            db_update["model_id"] = request_dict["modelId"]
        if "modelVersion" in request_dict:
            # Validate new model version exists
            from repositories.model_repository import ModelRepository
            from config import settings
            repo = ModelRepository(db)
            new_model = await repo.find_by_model_id_and_version(request.modelId, request_dict["modelVersion"])
            if not new_model:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model with ID {request.modelId} version {request_dict['modelVersion']} does not exist, cannot update service."
                )
            # Check if deprecated
            if new_model.version_status == "deprecated" and not settings.ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model version {request.modelId} v{request_dict['modelVersion']} is deprecated and cannot be used for services."
                )
            db_update["model_version"] = request_dict["modelVersion"]
            db_update["version_updated_at"] = int(time.time())
        if "healthStatus" in request_dict:
            db_update["health_status"] = _json_safe(request_dict["healthStatus"])
        if "benchmarks" in request_dict:
            db_update["benchmarks"] = _json_safe(request_dict["benchmarks"])
        # languagePair is not persisted on services table; skip

        if not db_update:
            logger.warning("No valid update fields provided for service update")
            return 0

        # 2. Update DB
        stmt_select = select(Service).where(Service.service_id == request.serviceId)
        result = await db.execute(stmt_select)
        db_service = result.scalars().first()

        if db_service is None:
            logger.warning(f"No DB record found for service {request.serviceId}")
            return 0
        
        # Model version validation is already done above if modelVersion is being updated
        # If only modelId is being updated (without modelVersion), validate the existing model version
        if "modelId" in request_dict and "modelVersion" not in request_dict:
            from repositories.model_repository import ModelRepository
            repo = ModelRepository(db)
            # Get current service to check its model_version
            stmt_select = select(Service).where(Service.service_id == request.serviceId)
            result = await db.execute(stmt_select)
            db_service = result.scalars().first()
            if db_service:
                model_exists = await repo.find_by_model_id_and_version(request.modelId, db_service.model_version)
                if not model_exists:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Model with ID {request.modelId} version {db_service.model_version} does not exist, cannot update service."
                    )
        
        stmt_update = (
            update(Service)
            .where(Service.service_id == request.serviceId)
            .values(**db_update)
        )

        await db.execute(stmt_update)
        await db.commit()

        logger.info(f"Service {request.serviceId} updated in DB: {db_update}")

        # 3. Update Redis cache
        # Try to get existing cache, or fetch from DB if cache doesn't exist
        try:
            cache = ServiceCache.get(request.serviceId)
            # Cache exists, patch it
            new_cache = cache.model_dump()
            cache_fields = cache.__class__.model_fields

            # Patch only valid cache fields
            for key, value in request_dict.items():
                if key in cache_fields:
                    new_cache[key] = value
        except Exception:
            # Cache doesn't exist, fetch from DB and create cache entry
            logger.info(f"Service {request.serviceId} not found in cache, fetching from DB to create cache entry")
            try:
                # Refresh to get updated data
                await db.refresh(db_service)
                
                # Convert DB model to cache format
                new_cache = _json_safe({
                    "serviceId": db_service.service_id,
                    "name": db_service.name,
                    "serviceDescription": db_service.service_description,
                    "hardwareDescription": db_service.hardware_description,
                    "publishedOn": db_service.published_on,
                    "modelId": db_service.model_id,
                    "endpoint": db_service.endpoint,
                    "apiKey": db_service.api_key,
                    "healthStatus": db_service.health_status or {},
                    "benchmarks": db_service.benchmarks or {},
                })
                
                # Apply updates to the fetched data
                for key, value in request_dict.items():
                    if key != "serviceId" and value is not None:
                        # Map to cache field names
                        if key == "serviceDescription":
                            new_cache["serviceDescription"] = value
                        elif key == "hardwareDescription":
                            new_cache["hardwareDescription"] = value
                        elif key == "api_key":
                            new_cache["apiKey"] = value
                        elif key == "modelId":
                            new_cache["modelId"] = value
                        elif key in cache_fields:
                            new_cache[key] = value
            except Exception as e:
                logger.exception(f"Error fetching service from DB for cache: {e}")
                return 1

        # Save updated cache
        try:
            updated_cache = ServiceCache(**new_cache)
            updated_cache.save()
            logger.info(f"Service {request.serviceId} cache refreshed")
        except Exception as e:
            logger.warning(f"Cache update failed for service {request.serviceId}: {e}")

        return 1

    except Exception as e:
        db.rollback()
        logger.exception("Error updating service")
        raise e
    finally:
        await db.close()

async def delete_service_by_uuid(id_str: str) -> int:
    """Delete service by UUID (id)"""
   
    db: AsyncSession = AppDatabase()

    try:
        try:
            uuid = UUID(id_str)
        except ValueError:
            logger.warning(f"Invalid UUID provided for delete: {id_str}")
            return 0

        result = await db.execute(select(Service).where(Service.id == uuid))
        service = result.scalars().first()

        if not service:
            logger.warning(f"Model with UUID {uuid} not found for delete.")
            return 0

        service_id = service.service_id

        try:
            cache_entry = ServiceCache.get(service_id)

            if cache_entry:
                ServiceCache.delete(service_id)
                logger.info(f"Cache deleted for serviceId='{service_id}'")

        except Exception as cache_err:
            logger.warning(f"ServiceCache delete failed for {uuid}: {cache_err}")


        await db.execute(delete(Service).where(Service.id == uuid))
        await db.commit()

        logger.info(f"DB: Service with ID {uuid} deleted successfully.")

        return 1
    except Exception as e:
        await db.rollback()
        logger.exception("Error deleting service from DB.")
        raise Exception("Delete failed due to internal DB error") from e
    finally:
        await db.close()


async def get_service_details(service_id: str) -> Dict[str, Any]:
    """
    Full service view API
    """

    logger.info(f"Fetching service view for: {service_id}")

    db: AsyncSession = AppDatabase()

    try:

        result = await db.execute(select(Service).where(Service.service_id == service_id))
        service = result.scalars().first()

        if not service:
            # Fallback: try to find by UUID if serviceId happens to be a UUID
            try:
                uuid = UUID(service_id)
                result = await db.execute(select(Service).where(Service.id == uuid))
                service = result.scalars().first()
            except Exception:
                pass

        if not service:
            logger.warning(f"Service not found for ID: {service_id}")
            raise HTTPException(status_code=404, detail="Service not found")

        # Get model by model_id and model_version (composite key)
        from repositories.model_repository import ModelRepository
        repo = ModelRepository(db)
        model = await repo.find_by_model_id_and_version(service.model_id, service.model_version)

        if not model:
            raise HTTPException(
                status_code=404, 
                detail=f"Model with ID {service.model_id} version {service.model_version} does not exist"
            )
        
        # Get available versions for this model (compute before constructing service_dict)
        all_versions = await repo.find_all_versions(service.model_id)
        available_versions = [v.version for v in all_versions]

        # Convert service SQLAlchemy → dict
        service_dict = {
            "serviceId": service.service_id,
            "uuid": str(service.id),
            "name": service.name,
            "serviceDescription": service.service_description,
            "hardwareDescription": service.hardware_description,
            "publishedOn": service.published_on,
            "modelId": service.model_id,
            "modelVersion": service.model_version,
            "endpoint": service.endpoint,
            "api_key": service.api_key,
            "healthStatus": service.health_status,
            "benchmarks": service.benchmarks,
            "availableVersions": available_versions,
        }

        # Convert model SQLAlchemy → request format
        model_payload = ModelCreateRequest(
            modelId=model.model_id,
            version=model.version,
            submittedOn=model.submitted_on,
            updatedOn=model.updated_on,
            name=model.name,
            description=model.description,
            refUrl=model.ref_url,
            task=model.task,
            languages=model.languages,
            license=model.license,
            domain=model.domain,
            inferenceEndPoint=model.inference_endpoint,
            benchmarks=model.benchmarks,
            submitter=model.submitter,
        )
        # 3. API Key + Usage — COMMENTED OUT FOR NOW
        # api_keys = []
        # total_usage = 0
        #
        # # TODO: Uncomment once ApiKey, Usage models exist
        # key_rows = db.query(ApiKey).all()
        #
        # for k in key_rows:
        #     usage_entries = (
        #         db.query(ServiceUsage)
        #           .filter(ServiceUsage.key_id == k.id)
        #           .all()
        #     )
        #
        #     service_usage_list = [
        #         {"service_id": u.service_id, "usage": u.usage}
        #         for u in usage_entries
        #     ]
        #
        #     total_usage += sum([u.usage for u in usage_entries])
        #
        #     api_keys.append(
        #         _ApiKey(
        #             id=str(k.id),
        #             name=k.name,
        #             masked_key=k.masked_key,
        #             active=k.active,
        #             type=k.key_type,
        #             created_timestamp=k.created_timestamp,
        #             services=service_usage_list,
        #             data_tracking=k.data_tracking,
        #         )
        #     )

        # Provide empty since API key system is not ready now
        api_keys = []
        total_usage = 0

        response = ServiceViewResponse(
            **service_dict,
            model=model_payload,
            key_usage=api_keys,
            total_usage=total_usage
        )

        return response

    except Exception as e:
        logger.exception(f"Error fetching service {service_id} details from DB.")
        raise e
    finally:
        await db.close()



async def list_all_services(task_type: TaskTypeEnum | None, model_version: Optional[str] = None, version_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch all service records from DB and convert to response format."""

    db: AsyncSession = AppDatabase()

    try:
        # Join Service with Model on composite key (model_id AND model_version)
        query = select(Service, Model).join(
            Model, 
            (Model.model_id == Service.model_id) & (Model.version == Service.model_version)
        )

        if task_type:
            query = query.where(Model.task['type'].astext == task_type.value)
        if model_version:
            query = query.where(Service.model_version == model_version)
        if version_status:
            query = query.where(Model.version_status == version_status)

        try:
            result = await db.execute(query)
            rows = result.fetchall()
        except Exception as e:
            logger.error(f"[DB] Failed to fetch services: {str(e)}")
            raise

        if not rows:
            logger.info(f"[DB] No services found for type :{task_type.value if task_type else None}")
            return None

        services_list = []

        for service, model in rows:
            if not model:
                logger.error(
                    f"[DB] Failed to get model details from db for service {service.service_id}"
                )
                return None
            
            
            services_list.append(
                ServiceListResponse(
                    serviceId=str(service.service_id),
                    uuid=str(service.id),
                    name=service.name,
                    serviceDescription=getattr(service, "service_description", None),
                    hardwareDescription=getattr(service, "hardware_description", None),
                    publishedOn=getattr(service, "published_on", None),
                    modelId=service.model_id,
                    modelVersion=getattr(service, "model_version", None),
                    # Persist service endpoint and api key details
                    endpoint=getattr(service, "endpoint", None),
                    healthStatus=getattr(service, "health_status", None),
                    benchmarks=getattr(service, "benchmarks", None),

                    # From MODEL table
                    task=getattr(model, "task", {}) if model else {},
                    languages=getattr(model, "languages", []) if model else []
                )
            )

        return services_list

    except Exception as e:
        logger.error(f"[DB] Error fetching service list: {str(e)}")
        raise
    finally:
        await db.close()



async def update_service_health(payload: ServiceHeartbeatRequest):
    """
    Update service health status based on heartbeat request.
    """

    logger.info(f"Updating health status for service: {payload.serviceId}")

    db: AsyncSession = AppDatabase()

    try:
        result = await db.execute(select(Service).where(Service.service_id == payload.serviceId))
        service = result.scalars().first()

        if not service:
            logger.warning(f"Service not found for ID: {payload.serviceId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in database"
            )

        service_dict = {
            "id": str(service.id),
            "service_id": service.service_id,
            "name": service.name,
            "service_description": service.service_description,
            "hardware_description": service.hardware_description,
            "published_on": service.published_on,
            "model_id": service.model_id,
            "endpoint": service.endpoint,
            "api_key": service.api_key,
            "health_status": service.health_status,
            "benchmarks": service.benchmarks,
            "created_at": service.created_at.isoformat() if service.created_at else None,
            "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        }

        if not service_dict.get("health_status") or service_dict["health_status"] is None:
            service_dict["health_status"] = {}

        service_dict["health_status"]["status"] = payload.status
        service_dict["health_status"]["lastUpdated"] = str(datetime.now())

        update_data = {
            "health_status": service_dict["health_status"]
        }

        service_id = service.id
        if isinstance(service_id, str):
            try:
                service_id = UUID(service_id)
            except ValueError:
                logger.error("Invalid UUID in service.id")
                return 0

        stmt = (
            update(Service)
            .where(Service.id == service_id)
            .values(health_status=update_data)
        )
        
        await db.execute(stmt)
        await db.commit()

        db.commit()
        logger.info(f"Service {payload.serviceId} health status updated to {payload.status}")

        return 1

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error updating service health status.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Service health update not successful"}
        ) from e
    finally:
        await db.close()

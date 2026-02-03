from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select , delete , update, func as sql_func, and_, case, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import Dict, Any, List, Optional
import os
import hashlib

from models.db_models import Model , Service, VersionStatus, Experiment, ExperimentVariant, ExperimentStatus
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

MAX_ACTIVE_VERSIONS_PER_MODEL = int(os.getenv("MAX_ACTIVE_VERSIONS_PER_MODEL", "5"))
ALLOW_DEPRECATED_MODEL_CHANGES = os.getenv("ALLOW_DEPRECATED_MODEL_CHANGES", "true").lower() == "true"


def generate_model_id(model_name: str, version: str) -> str:
    """
    Generate a deterministic model_id hash from model_name and version.
    Uses SHA256 for enterprise-standard hashing, truncated to 32 characters.
    
    Args:
        model_name: The name of the model
        version: The version of the model
        
    Returns:
        A hexadecimal hash string (32 characters, first half of SHA256)
    """
    # Normalize inputs: strip whitespace and convert to lowercase for consistency
    normalized_name = model_name.strip().lower()
    normalized_version = version.strip().lower()
    
    # Create a deterministic string from name and version
    hash_input = f"{normalized_name}:{normalized_version}"
    
    # Generate SHA256 hash
    hash_obj = hashlib.sha256(hash_input.encode('utf-8'))
    full_hash = hash_obj.hexdigest()
    
    # Truncate to 32 characters (first half of SHA256)
    model_id = full_hash[:32]
    
    return model_id


def generate_service_id(model_name: str, model_version: str, service_name: str) -> str:
    """
    Generate a deterministic service_id hash from model_name, model_version, and service_name.
    Uses SHA256 for enterprise-standard hashing, truncated to 32 characters.
    
    Args:
        model_name: The name of the model
        model_version: The version of the model
        service_name: The name of the service
        
    Returns:
        A hexadecimal hash string (32 characters, first half of SHA256)
    """
    # Normalize inputs: strip whitespace and convert to lowercase for consistency
    normalized_model_name = model_name.strip().lower()
    normalized_model_version = model_version.strip().lower()
    normalized_service_name = service_name.strip().lower()
    
    # Create a deterministic string from model_name, model_version, and service_name
    hash_input = f"{normalized_model_name}:{normalized_model_version}:{normalized_service_name}"
    
    # Generate SHA256 hash
    hash_obj = hashlib.sha256(hash_input.encode('utf-8'))
    full_hash = hash_obj.hexdigest()
    
    # Truncate to 32 characters (first half of SHA256)
    service_id = full_hash[:32]
    
    return service_id


async def is_model_version_used_by_published_service(model_id: str, version: str) -> tuple[bool, List[str]]:
    """
    Check if a specific model version is being used by any published service.
    
    Args:
        model_id: The model ID to check
        version: The version to check
        
    Returns:
        Tuple of (is_used, list_of_service_ids) - is_used is True if the model version
        is being used by at least one published service, along with the list of service IDs
    """
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Service.service_id).where(
            Service.model_id == model_id,
            Service.model_version == version,
            Service.is_published == True
        )
        result = await db.execute(stmt)
        service_ids = [row[0] for row in result.fetchall()]
        
        return len(service_ids) > 0, service_ids
    except Exception as e:
        logger.error(f"Error checking if model version is used by published service: {e}")
        raise
    finally:
        await db.close()



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
    

async def save_model_to_db(payload: ModelCreateRequest, created_by: str = None):
    """
    Save a new model entry to the database.
    Includes:
      - Generate model_id from hash of (name, version)
      - Duplicate (name, version) check
      - Max active versions enforcement
      - Record creation
      - Commit / rollback

    Args:
        payload: Model creation request data
        created_by: User ID (string) who is creating this model (optional)
    """
    db: AsyncSession = AppDatabase()
    try:
        # Generate model_id from hash of (name, version)
        generated_model_id = generate_model_id(payload.name, payload.version)
        
        # Pre-check for duplicates: check if (name, version) combination already exists
        # Since model_id is now a hash of (name, version), checking by name and version ensures uniqueness
        stmt = select(Model).where(
            Model.name == payload.name,
            Model.version == payload.version
        )
        result = await db.execute(stmt)
        existing = result.scalar()

        if existing:
            logger.warning(f"Duplicate model name and version: {payload.name} v{payload.version}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model with name '{payload.name}' and version '{payload.version}' already exists."
            )
        
        # Check max active versions if this version is being created as ACTIVE
        version_status = payload.versionStatus if hasattr(payload, 'versionStatus') and payload.versionStatus else VersionStatus.ACTIVE
        if version_status == VersionStatus.ACTIVE:
            # Count active versions for this model (by name, since model_id is now a hash)
            # We need to find all models with the same name and count active versions
            active_count_stmt = select(sql_func.count(Model.id)).where(
                Model.name == payload.name,
                Model.version_status == VersionStatus.ACTIVE
            )
            active_count_result = await db.execute(active_count_stmt)
            active_count = active_count_result.scalar() or 0
            
            if active_count >= MAX_ACTIVE_VERSIONS_PER_MODEL:
                logger.warning(
                    f"Max active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model '{payload.name}'. "
                    f"Current active versions: {active_count}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum number of active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model '{payload.name}'. "
                           f"Please deprecate an existing active version before creating a new one."
                )
        
        payload_dict = _json_safe(payload)

        now_epoch = int(time.time())

        payload_dict["submittedOn"] = now_epoch
        payload_dict["updatedOn"] = None
        payload_dict["modelId"] = generated_model_id  # Add generated model_id to payload_dict for cache

        # Create new model record
        new_model = Model(
            model_id=generated_model_id,
            version=payload_dict.get("version"),
            version_status=version_status,
            version_status_updated_at=datetime.now(),
            submitted_on=payload_dict.get("submittedOn"),
            updated_on=None,  # Null on creation, will be set on updates
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
            created_by=created_by,
        )

        db.add(new_model)
        await db.commit()
        await db.refresh(new_model)
        logger.info(f"Model '{payload.name}' (ID: {generated_model_id}) v{payload.version} successfully saved to DB.")

        # Cache the model in Redis
        try:
            payload_dict = model_redis_safe_payload(payload_dict)
            cache_entry = ModelCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Model {new_model.model_id} v{new_model.version} cached in Redis.")
        except Exception as ce:
            logger.warning(f"Could not cache model {new_model.model_id} v{new_model.version}: {ce}")

        return generated_model_id

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

        logger.info(f"update_by_filter: Found {len(records)} record(s) matching filters {filters}")
        
        if not records:
            logger.warning(f"update_by_filter: No records found matching filters {filters}")
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
            logger.debug(f"update_by_filter: Updating record {record.id} (model_id={record.model_id}, version={record.version})")
            for field, value in data.items():
                old_value = getattr(record, field, None)
                setattr(record, field, value)
                logger.debug(f"update_by_filter: Field '{field}' changed from {old_value} to {value}")

                # MUST DO THIS for JSONB fields
                if field in json_fields:
                    flag_modified(record, field)

        logger.info(f"update_by_filter: Committing changes for {len(records)} record(s)")
        await db.commit()
        logger.info(f"update_by_filter: Successfully updated {len(records)} record(s)")
        return len(records)

    except Exception as e:
        await db.rollback()
        logger.exception("Failed to update records.")
        raise ValueError(f"Failed to update records: {e}") from e
    finally:
        await db.close()


async def update_model(payload: ModelUpdateRequest, updated_by: str = None):
    """
    Update model record in PostgreSQL and refresh Redis cache.
    Note: modelId and version are used as identifiers to identify which version to update.
    
    Model versions associated with published services are immutable and cannot be updated.
    
    Args:
        payload: Model update request data
        updated_by: User ID (string) who is updating this model (optional)
    """

    if not payload.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Version is required to update a specific model version."
        )

    logger.info(f"Attempting to update model: {payload.modelId} v{payload.version}")

    # Check if model version is used by any published service (immutability check)
    is_immutable, published_service_ids = await is_model_version_used_by_published_service(
        payload.modelId, payload.version
    )
    if is_immutable:
        logger.warning(
            f"Cannot update model {payload.modelId} v{payload.version}: "
            f"Used by published services: {published_service_ids}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "kind": "ImmutableModelVersion",
                "message": f"Model version '{payload.modelId}' v{payload.version} cannot be modified because it is "
                           f"associated with {len(published_service_ids)} published service(s): {', '.join(published_service_ids)}. "
                           f"Unpublish the service(s) first to modify this model version."
            }
        )

    # Use exclude_unset=True for PATCH semantics - include fields that are explicitly set
    request_dict = payload.model_dump(exclude_unset=True)
    logger.info(f"Request dict from payload (exclude_unset=True): {request_dict}")
    logger.info(f"Payload versionStatus value: {payload.versionStatus} (type: {type(payload.versionStatus)})")
    now_epoch = int(time.time())

    db: AsyncSession = AppDatabase()
    try:
        # Check if model version exists
        stmt = select(Model).where(
            Model.model_id == payload.modelId,
            Model.version == payload.version
        )
        result = await db.execute(stmt)
        existing_model = result.scalar()
        
        if not existing_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model with ID {payload.modelId} and version {payload.version} not found."
            )

        # Check if model is DEPRECATED and updates are not allowed
        if existing_model.version_status == VersionStatus.DEPRECATED and not ALLOW_DEPRECATED_MODEL_CHANGES:
            logger.warning(
                f"Cannot update model {payload.modelId} v{payload.version}: "
                f"Model status is DEPRECATED"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "kind": "DeprecatedModelUpdateNotAllowed",
                    "message": f"Model version '{payload.modelId}' v{payload.version} cannot be modified because it is "
                               f"DEPRECATED and ALLOW_DEPRECATED_MODEL_CHANGES is set to false."
                }
            )

        # Check max active versions if changing status to ACTIVE
        # Use payload.versionStatus directly to handle both enum and string values
        is_setting_active = False
        if payload.versionStatus is not None:
            if isinstance(payload.versionStatus, VersionStatus):
                is_setting_active = payload.versionStatus == VersionStatus.ACTIVE
            elif isinstance(payload.versionStatus, str):
                is_setting_active = payload.versionStatus.upper() == "ACTIVE"
        
        if is_setting_active and existing_model.version_status != VersionStatus.ACTIVE:
            # Changing from non-ACTIVE to ACTIVE - check the limit
            # Count active versions for this model_id (excluding current version)
            active_count_stmt = select(sql_func.count(Model.id)).where(
                Model.model_id == payload.modelId,
                Model.version_status == VersionStatus.ACTIVE,
                Model.version != payload.version  # Exclude current version
            )
            active_count_result = await db.execute(active_count_stmt)
            active_count = active_count_result.scalar() or 0
            
            logger.info(f"Max active versions check: model={payload.modelId}, current_active={active_count}, limit={MAX_ACTIVE_VERSIONS_PER_MODEL}")
            
            if active_count >= MAX_ACTIVE_VERSIONS_PER_MODEL:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum number of active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model {payload.modelId}. "
                           f"Please deprecate an existing active version before activating this one."
                )

        # 1. Update DB first
        postgres_data = {}

        # Handle versionStatus separately - check payload directly to ensure we catch it
        if payload.versionStatus is not None:
            if isinstance(payload.versionStatus, VersionStatus):
                postgres_data["version_status"] = payload.versionStatus
            elif isinstance(payload.versionStatus, str):
                postgres_data["version_status"] = VersionStatus(payload.versionStatus)
            else:
                postgres_data["version_status"] = payload.versionStatus
            postgres_data["version_status_updated_at"] = datetime.now()
            logger.info(f"Setting version_status to {postgres_data['version_status']} (type: {type(postgres_data['version_status'])}) from payload.versionStatus")

        for key, value in request_dict.items():
            # Skip modelId and version (used only for filtering, not updated)
            if key in ("modelId", "version"):
                continue

            # Skip versionStatus as we handle it above
            if key == "versionStatus":
                continue

            # Prevent name updates - model_id is a hash of (name, version), so changing name would break model_id
            if key == "name":
                logger.warning(f"Attempted to update name for model {payload.modelId} v{payload.version}. Name updates are not allowed as model_id is derived from name and version.")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Model name cannot be updated. Model ID is derived from name and version. Create a new model version with the new name instead."
                )

            # Skip None values for PATCH
            if value is None:
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
        if updated_by is not None:
            postgres_data["updated_by"] = updated_by
        logger.info(f"Updating DB for model {payload.modelId} v{payload.version} with fields: {list(postgres_data.keys())}")
        logger.debug(f"DB update data: {postgres_data}")

        # 2. Repository update - filter by both model_id and version
        result = await update_by_filter(
            {"model_id": payload.modelId, "version": payload.version}, 
            postgres_data
        )
        
        if result == 0:
            logger.error(f"update_model: No records were updated for model {payload.modelId} v{payload.version}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No records found or updated for model {payload.modelId} version {payload.version}"
            )
        
        logger.info(f"update_model: Successfully updated {result} record(s) for model {payload.modelId} v{payload.version}")
            
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error updating model {payload.modelId} v{payload.version}")
        raise
    finally:
        await db.close()

    # 3. Update Redis cache
    # Note: Cache key might need to include version for proper versioning support
    # For now, we'll refresh from DB
    db_cache: AsyncSession = AppDatabase()
    try:
        stmt = select(Model).where(
            Model.model_id == payload.modelId,
            Model.version == payload.version
        )
        result_db = await db_cache.execute(stmt)
        db_model = result_db.scalar()
        
        if db_model:
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
            })
            
            # Convert to Redis-safe format and save
            try:
                new_cache = model_redis_safe_payload(new_cache)
                updated_cache = ModelCache(**new_cache)
                updated_cache.save()
                logger.info(f"Cache updated for model {payload.modelId} v{payload.version}")
            except Exception as ce:
                logger.warning(f"Failed to update cache for {payload.modelId} v{payload.version}: {ce}")
    except Exception as e:
        logger.exception(f"Error fetching model from DB for cache: {e}")
    finally:
        await db_cache.close()

    logger.info(f"Model {payload.modelId} v{payload.version} successfully updated.")

    return result





async def delete_model_by_uuid(id_str: str) -> int:
    """
    Delete model by internal UUID (id).
    
    Model versions associated with published services are immutable and cannot be deleted.
    Unpublished services associated with the model version will be automatically deleted.
    """

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
        model_version = model.version

        # Check if model version is used by any published service (immutability check)
        is_immutable, published_service_ids = await is_model_version_used_by_published_service(
            model_id, model_version
        )
        if is_immutable:
            logger.warning(
                f"Cannot delete model {model_id} v{model_version}: "
                f"Used by published services: {published_service_ids}"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "kind": "ImmutableModelVersion",
                    "message": f"Model version '{model_id}' v{model_version} cannot be deleted because it is "
                               f"associated with {len(published_service_ids)} published service(s): {', '.join(published_service_ids)}. "
                               f"Unpublish the service(s) first to delete this model version."
                }
            )

        # ---- Delete unpublished services associated with this model version ----
        # Find unpublished services to clear their cache entries
        unpublished_services_result = await db.execute(
            select(Service.service_id).where(
                Service.model_id == model_id,
                Service.model_version == model_version,
                Service.is_published == False
            )
        )
        unpublished_service_ids = [row[0] for row in unpublished_services_result.fetchall()]
        
        if unpublished_service_ids:
            # Clear cache for unpublished services
            for service_id in unpublished_service_ids:
                try:
                    cache_entry = ServiceCache.get(service_id)
                    if cache_entry:
                        ServiceCache.delete(service_id)
                        logger.info(f"Cache deleted for serviceId='{service_id}'")
                except Exception as cache_err:
                    logger.warning(f"ServiceCache delete failed for {service_id}: {cache_err}")
            
            # Delete unpublished services from DB
            await db.execute(
                delete(Service).where(
                    Service.model_id == model_id,
                    Service.model_version == model_version,
                    Service.is_published == False
                )
            )
            logger.info(
                f"Deleted {len(unpublished_service_ids)} unpublished service(s) associated with "
                f"model {model_id} v{model_version}: {unpublished_service_ids}"
            )

        # ---- Delete from Cache ----
        try:
            cache_entry = ModelCache.get(model_id)

            if cache_entry:
                ModelCache.delete(model_id)
                logger.info(f"Cache deleted for modelId='{model_id}'")

        except Exception as cache_err:
            logger.warning(f"ModelCache delete failed for {uuid}: {cache_err}")


        await db.execute(delete(Model).where(Model.id == uuid))

        await db.commit()
        logger.info(f"DB: Model with ID {uuid} deleted successfully.")

        return 1
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Error deleting model from DB.")
        raise Exception("Delete failed due to internal DB error") from e
    finally:
        await db.close()



async def get_model_details(model_id: str, version: str = None) -> Dict[str, Any]:
    """
    Get model details by model_id. If version is provided, returns that specific version.
    If version is not provided, returns the latest ACTIVE version first, then falls back to
    latest DEPRECATED version if no ACTIVE versions exist.
    
    Ordering priority:
    1. ACTIVE versions first
    2. Within same status, ordered by submitted_on descending (latest first)
    """
    db: AsyncSession = AppDatabase()
    try:
        query = select(Model).where(Model.model_id == model_id)
        if version:
            # Specific version requested
            query = query.where(Model.version == version)
        else:
            # No version specified - prioritize ACTIVE versions, then latest by submitted_on
            # Use case() to prioritize ACTIVE (0) over DEPRECATED (1)
            status_priority = case(
                (Model.version_status == VersionStatus.ACTIVE, 0),
                else_=1
            )
            query = query.order_by(
                status_priority,  # ACTIVE first
                desc(Model.submitted_on)  # Latest first within same status
            )
        
        result = await db.execute(query)
        model = result.scalars().first()

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

        return {
            "modelId": model.model_id,
            "uuid": str(model.id),
            "name": model.name,
            "version": model.version,
            "versionStatus": model.version_status.value if model.version_status else None,
            "versionStatusUpdatedAt": model.version_status_updated_at.isoformat() if model.version_status_updated_at else None,
            "description": model.description,
            "languages": model.languages or [],
            "domain": model.domain,
            "submitter": model.submitter,
            "license": model.license,
            "inferenceEndPoint": model.inference_endpoint,
            "source": model.ref_url or "",
            "task": model.task,
            "createdBy": model.created_by,
            "updatedBy": model.updated_by,
         }
     
    except Exception as e:
         logger.error(f"[DB] Error fetching model details: {str(e)}")
         raise
    finally:
         await db.close()
    

async def list_all_models(task_type: TaskTypeEnum | None, include_deprecated: bool = True, model_name: str | None = None, created_by: str | None = None) -> List[Dict[str, Any]]:
    """
    Fetch all model records from DB and convert to response format.
    
    Args:
        task_type: Optional filter by task type (asr, nmt, tts, etc.)
        include_deprecated: If False, only returns ACTIVE versions. Defaults to True.
        model_name: Optional filter by model name. Returns all versions of models matching this name.
        created_by: Optional filter by user ID (string) who created the model.
    
    Ordering:
    1. By submitted_on descending (latest first) - primary sort
    2. ACTIVE versions first within same submitted_on
    3. By model_id as final tiebreaker
    """

    db: AsyncSession = AppDatabase()
    try:
        # Prioritize ACTIVE versions
        status_priority = case(
            (Model.version_status == VersionStatus.ACTIVE, 0),
            else_=1
        )
        
        query = select(Model)
        
        # Filter by task type if provided
        if task_type:
            query = query.where(Model.task['type'].astext == task_type.value)
        
        # Filter by model name if provided (case-insensitive match)
        if model_name:
            query = query.where(sql_func.lower(Model.name) == sql_func.lower(model_name))
        
        # Filter out deprecated versions if requested
        if not include_deprecated:
            query = query.where(Model.version_status == VersionStatus.ACTIVE)
        
        # Filter by created_by if provided
        if created_by is not None:
            query = query.where(Model.created_by == created_by)
        
        # Order by submitted_on descending (latest first), then ACTIVE first, then model_id
        query = query.order_by(
            desc(Model.submitted_on),
            status_priority,
            Model.model_id
        )

        result = await db.execute(query)
        models = result.scalars().all()

        if not models:
            logger.info(f"[DB] No models found for type :{task_type}")
            return None

        result = []
        for item in models:
            # Convert SQLAlchemy model → dict
            data = item.__dict__.copy()
            data.pop("_sa_instance_state", None)

            # Extract version_status - it's an enum, need to get its value
            version_status = data.get("version_status")
            version_status_value = version_status.value if version_status else None
            
            # Extract version_status_updated_at
            version_status_updated_at = data.get("version_status_updated_at")
            version_status_updated_at_str = version_status_updated_at.isoformat() if version_status_updated_at else None

            # Build response object
            result.append({
                "modelId": str(data.get("model_id")),
                "uuid": str(data.get("id")),
                "name": data.get("name"),
                "version": data.get("version"),
                "versionStatus": version_status_value,
                "versionStatusUpdatedAt": version_status_updated_at_str,
                "description": data.get("description"),
                "languages": data.get("languages") or [],
                "domain": data.get("domain"),
                "submitter": data.get("submitter"),
                "license": data.get("license"),
                "inferenceEndPoint": data.get("inference_endpoint"),
                "source": data.get("ref_url"),
                "task": data.get("task", {}),
                "createdBy": data.get("created_by"),
                "updatedBy": data.get("updated_by"),
            })

        return result
    except Exception as e:
        logger.error(f"[DB] Error fetching model list: {str(e)}")
        raise
    finally:
        await db.close()


####################################################### Service Functions #######################################################


async def save_service_to_db(payload: ServiceCreateRequest, created_by: str = None):
    """
    Save a new service entry to the database.
    Includes:
      - Look up model to get model_name
      - Generate service_id from hash of (model_name, model_version, service_name)
      - Duplicate (model_id, model_version, name) check
      - Record creation
      - Commit / rollback
    
    Args:
        payload: Service creation request data
        created_by: User ID (string) who is creating this service (optional)
    """
    db: AsyncSession = AppDatabase()
    try:
        # Check if associated model version exists and get model_name
        result = await db.execute(
            select(Model).where(
                Model.model_id == payload.modelId,
                Model.version == payload.modelVersion
            )
        )
        model = result.scalars().first()
        if not model:
            raise HTTPException(
                status_code=400,
                detail=f"Model with ID {payload.modelId} and version {payload.modelVersion} does not exist, cannot create service."
            )
        
        # Generate service_id from hash of (model_name, model_version, service_name)
        generated_service_id = generate_service_id(model.name, payload.modelVersion, payload.name)
        
        # Pre-check for duplicates: check if (model_id, model_version, name) combination already exists
        # Since service_id is now a hash of (model_name, model_version, service_name), this ensures uniqueness
        stmt = select(Service).where(
            Service.model_id == payload.modelId,
            Service.model_version == payload.modelVersion,
            Service.name == payload.name
        )
        result = await db.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            logger.warning(f"Duplicate service: model_id={payload.modelId}, model_version={payload.modelVersion}, name={payload.name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service with name '{payload.name}' for model '{model.name}' version '{payload.modelVersion}' already exists."
            )
        
        payload_dict = _json_safe(payload.model_dump(by_alias=True))

        now_epoch = int(time.time())
        
        # Auto-generate publishedOn if not provided
        if not payload_dict.get("publishedOn"):
            payload_dict["publishedOn"] = now_epoch
        
        # Add generated service_id to payload_dict for cache
        payload_dict["serviceId"] = generated_service_id

        # Handle isPublished - default to False if not provided
        is_published = payload_dict.get("isPublished", False)
        published_at = int(time.time()) if is_published else None
        
        new_service = Service(
            service_id=generated_service_id,
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
            is_published=is_published,
            published_at=published_at,
            created_by=created_by,
        )
        db.add(new_service)
        await db.commit()
        await db.refresh(new_service)
        logger.info(f"Service '{payload.name}' (ID: {generated_service_id}) for model '{model.name}' v{payload.modelVersion} successfully saved to DB.")


        # Cache the service in Redis
        try:
            cache_entry = ServiceCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Service {new_service.service_id} cached in Redis.")
        except Exception as ce:
            logger.warning(f"Could not cache service {new_service.service_id}: {ce}")

        return generated_service_id

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error while saving service to DB.")
        raise Exception("Insert failed due to internal DB error") from e
    finally:
        await db.close()


async def update_service(request: ServiceUpdateRequest, updated_by: str = None):
    """
    Update an existing service record in PostgreSQL and refresh Redis cache.
    Note: serviceId is used as identifier and is NOT changed during update.
    Note: name, modelId, and modelVersion are NOT updatable since service_id is derived from them.
    
    Args:
        request: Service update request data
        updated_by: User ID (string) who is updating this service (optional)
    """

    db: AsyncSession = AppDatabase()

    try:
        if not request.serviceId:
            logger.warning("Missing serviceId in update request")
            return 0

        request_dict = request.model_dump(exclude_none=True,by_alias=True)

        # 1. Build DB update dict
        # Note: name, modelId, modelVersion are NOT updatable since service_id is derived from (model_name, model_version, service_name)
        db_update = {}
        
        # Track who made this update
        if updated_by is not None:
            db_update["updated_by"] = updated_by

        if "serviceDescription" in request_dict:
            db_update["service_description"] = request_dict["serviceDescription"]
        if "hardwareDescription" in request_dict:
            db_update["hardware_description"] = request_dict["hardwareDescription"]
        if "endpoint" in request_dict:
            db_update["endpoint"] = request_dict["endpoint"]
        if "api_key" in request_dict:
            db_update["api_key"] = request_dict["api_key"]
        if "healthStatus" in request_dict:
            db_update["health_status"] = _json_safe(request_dict["healthStatus"])
        if "benchmarks" in request_dict:
            db_update["benchmarks"] = _json_safe(request_dict["benchmarks"])
        # languagePair is not persisted on services table; skip
        
        # Handle isPublished - automatically set published_at/unpublished_at timestamps
        if "isPublished" in request_dict:
            is_published = request_dict["isPublished"]
            db_update["is_published"] = is_published
            now_epoch = int(time.time())
            if is_published:
                # Publishing: set published_at, clear unpublished_at
                db_update["published_at"] = now_epoch
                db_update["unpublished_at"] = None
                logger.info(f"Service {request.serviceId} will be published")
            else:
                # Unpublishing: set unpublished_at, keep published_at
                db_update["unpublished_at"] = now_epoch
                logger.info(f"Service {request.serviceId} will be unpublished")

        # 2. First check if service exists in DB
        stmt_select = select(Service).where(Service.service_id == request.serviceId)
        result = await db.execute(stmt_select)
        db_service = result.scalars().first()

        if db_service is None:
            logger.warning(f"No DB record found for service {request.serviceId}")
            return 0  # Service not found

        if not db_update:
            logger.warning("No valid update fields provided for service update. Valid fields: serviceDescription, hardwareDescription, endpoint, api_key, healthStatus, benchmarks, isPublished. Note: name, modelId, modelVersion are not updatable.")
            return -1  # No valid fields provided
        
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
    """
    Delete service by UUID (id).
    
    Published services cannot be deleted - they must be unpublished first.
    """
   
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
            logger.warning(f"Service with UUID {uuid} not found for delete.")
            return 0

        service_id = service.service_id

        # Check if service is published (cannot delete published services)
        if service.is_published:
            logger.warning(
                f"Cannot delete service {service_id}: Service is currently published"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "kind": "PublishedServiceCannotBeDeleted",
                    "message": f"Service '{service_id}' cannot be deleted because it is currently published. "
                               f"Unpublish the service first to delete it."
                }
            )

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
    except HTTPException:
        await db.rollback()
        raise
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

        # Convert service SQLAlchemy → dict
        service_dict = {
            "serviceId": service.service_id,
            "uuid": str(service.id),
            "name": service.name,
            "serviceDescription": service.service_description,
            "hardwareDescription": service.hardware_description,
            "publishedOn": service.published_on,
            "modelId": service.model_id,
            "endpoint": service.endpoint,
            "api_key": service.api_key,
            "healthStatus": service.health_status,
            "benchmarks": service.benchmarks,
            "isPublished": service.is_published,
            "publishedAt": datetime.fromtimestamp(service.published_at).isoformat() if service.published_at else None,
            "unpublishedAt": datetime.fromtimestamp(service.unpublished_at).isoformat() if service.unpublished_at else None,
            "createdBy": service.created_by,
            "updatedBy": service.updated_by,
        }

        result = await db.execute(
            select(Model).where(
                Model.model_id == service.model_id,
                Model.version == service.model_version
            )
        )
        model = result.scalars().first()

        if not model:
            raise HTTPException(
                status_code=404, 
                detail=f"Model with ID {service.model_id} and version {service.model_version} does not exist"
            )

        # Convert model SQLAlchemy → request format
        # Preserve all fields from inference_endpoint JSONB, including model_name and endpoint
        # Use model_dump_json and then parse back to preserve all fields including extras
        inference_endpoint_dict = dict(model.inference_endpoint) if model.inference_endpoint else {}
        
        # Create the model payload, but we'll override inferenceEndPoint after to preserve all fields
        model_payload_dict = {
            "modelId": model.model_id,
            "version": model.version,
            "submittedOn": model.submitted_on,
            "updatedOn": model.updated_on,
            "name": model.name,
            "description": model.description,
            "refUrl": model.ref_url,
            "task": model.task,
            "languages": model.languages,
            "license": model.license,
            "domain": model.domain,
            "inferenceEndPoint": inference_endpoint_dict,  # Use raw dict to preserve all fields
            "benchmarks": model.benchmarks,
            "submitter": model.submitter,
        }
        
        # Create ModelCreateRequest using model_construct to skip validation (data already exists in DB)
        model_payload = ModelCreateRequest.model_construct(**model_payload_dict)
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
        
        # Manually preserve inferenceEndPoint extra fields (model_name, endpoint) that Pydantic might drop
        # Convert response to dict, update inferenceEndPoint, then return dict
        response_dict = response.model_dump(mode='json', exclude_unset=False)
        if 'model' in response_dict and 'inferenceEndPoint' in response_dict['model']:
            # Merge original inference_endpoint dict to preserve all fields
            original_iep = dict(model.inference_endpoint) if model.inference_endpoint else {}
            current_iep = response_dict['model']['inferenceEndPoint']
            logger.info(f"Original IEP from DB: {original_iep}")
            logger.info(f"Current IEP from Pydantic: {current_iep}")
            # Preserve all fields from original (model_name, endpoint, etc.)
            # Overwrite current_iep with original to ensure all fields are preserved
            merged_iep = {**current_iep, **original_iep}  # Original takes precedence for extra fields
            response_dict['model']['inferenceEndPoint'] = merged_iep
            logger.info(f"Merged IEP: {merged_iep}, model_name: {merged_iep.get('model_name')}")
        
        return response_dict

    except Exception as e:
        logger.exception(f"Error fetching service {service_id} details from DB.")
        raise e
    finally:
        await db.close()



async def list_all_services(
    task_type: TaskTypeEnum | None, 
    is_published: bool | None = None,
    created_by: str | None = None
) -> List[Dict[str, Any]]:
    """
    Fetch all service records from DB and convert to response format.
    
    Args:
        task_type: Optional filter by task type (asr, nmt, tts, etc.)
        is_published: Optional filter by publish status. 
                      True = only published services, 
                      False = only unpublished services, 
                      None = all services (default)
        created_by: Optional filter by user ID (string) who created the service.
    """

    db: AsyncSession = AppDatabase()

    try:
        query = select(Service, Model).join(
            Model, 
            and_(
                Model.model_id == Service.model_id,
                Model.version == Service.model_version
            )
        )

        if task_type:
            query = query.where(Model.task['type'].astext == task_type.value)
        
        # Filter by publish status if provided
        if is_published is not None:
            query = query.where(Service.is_published == is_published)
        
        # Filter by created_by if provided
        if created_by is not None:
            query = query.where(Service.created_by == created_by)

        # Default sort: active (published) services first, then by most recently created
        query = query.order_by(desc(Service.is_published), desc(Service.created_at))

        try:
            result = await db.execute(query)
            rows = result.fetchall()
        except Exception as e:
            logger.error(f"[DB] Failed to fetch services: {str(e)}")
            raise

        if not rows:
            logger.info(f"[DB] No services found for type :{task_type.value}")
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
                    # Persist service endpoint and api key details
                    endpoint=getattr(service, "endpoint", None),
                    healthStatus=getattr(service, "health_status", None),
                    benchmarks=getattr(service, "benchmarks", None),
                    # Publish status fields
                    isPublished=getattr(service, "is_published", False),
                    publishedAt=datetime.fromtimestamp(service.published_at).isoformat() if service.published_at else None,
                    unpublishedAt=datetime.fromtimestamp(service.unpublished_at).isoformat() if service.unpublished_at else None,
                    # User tracking fields
                    createdBy=getattr(service, "created_by", None),
                    updatedBy=getattr(service, "updated_by", None),

                    # From MODEL table
                    task=getattr(model, "task", {}) if model else {},
                    languages=getattr(model, "languages", []) if model else [],
                    # Model version info
                    modelVersion=service.model_version,
                    versionStatus=model.version_status.value if model and model.version_status else None
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


async def publish_service(service_id: str):
    """
    Publish a service by setting is_published to True and updating published_at timestamp.
    """
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Service).where(Service.service_id == service_id)
        result = await db.execute(stmt)
        service = result.scalars().first()

        if not service:
            logger.warning(f"Service with ID {service_id} not found for publish.")
            return 0

        now_epoch = int(time.time())

        await db.execute(
            update(Service)
            .where(Service.service_id == service_id)
            .values(
                is_published=True,
                published_at=now_epoch,
                unpublished_at=None
            )
        )

        await db.commit()
        logger.info(f"Service {service_id} published successfully.")

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while publishing service.")
        raise Exception("Publish failed due to internal DB error") from e
    finally:
        await db.close()


async def unpublish_service(service_id: str):
    """
    Unpublish a service by setting is_published to False and updating unpublished_at timestamp.
    """
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Service).where(Service.service_id == service_id)
        result = await db.execute(stmt)
        service = result.scalars().first()

        if not service:
            logger.warning(f"Service with ID {service_id} not found for unpublish.")
            return 0

        now_epoch = int(time.time())

        await db.execute(
            update(Service)
            .where(Service.service_id == service_id)
            .values(
                is_published=False,
                unpublished_at=now_epoch
            )
        )

        await db.commit()
        logger.info(f"Service {service_id} unpublished successfully.")

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while unpublishing service.")
        raise Exception("Unpublish failed due to internal DB error") from e
    finally:
        await db.close()


# ============================================================================
# A/B Testing Experiment Operations
# ============================================================================

async def _check_duplicate_running_experiment(
    db: AsyncSession,
    experiment_id: UUID,
    variant_service_ids: set,
    task_type: Optional[List[str]],
    languages: Optional[List[str]],
    start_date: Optional[datetime],
    end_date: Optional[datetime]
) -> Optional[Experiment]:
    """
    Check if there's already a RUNNING experiment with the same configuration.
    
    Args:
        db: Database session
        experiment_id: ID of the experiment to check (exclude from search)
        variant_service_ids: Set of service IDs used in variants
        task_type: Task type filter
        languages: Languages filter
        start_date: Start date
        end_date: End date
        
    Returns:
        Existing RUNNING experiment with same config if found, None otherwise
    """
    # Find RUNNING experiments with overlapping date ranges (excluding current experiment)
    query = select(Experiment).where(
        Experiment.status == ExperimentStatus.RUNNING,
        Experiment.id != experiment_id
    )
    
    # Check for overlapping date ranges
    # Two date ranges overlap if: start1 <= end2 AND start2 <= end1
    # If start_date is None, treat it as starting now
    effective_start_date = start_date if start_date is not None else datetime.now()
    
    if end_date:
        # New experiment has both start and end dates
        date_overlap_condition = or_(
            Experiment.end_date.is_(None),
            Experiment.end_date >= effective_start_date
        )
        date_overlap_condition = and_(
            date_overlap_condition,
            or_(
                Experiment.start_date.is_(None),
                Experiment.start_date <= end_date
            )
        )
    else:
        # New experiment has start date but no end date (runs indefinitely)
        date_overlap_condition = or_(
            Experiment.end_date.is_(None),
            Experiment.end_date >= effective_start_date
        )
    
    query = query.where(date_overlap_condition)
    result = await db.execute(query)
    running_experiments = result.scalars().all()
    
    # Check each RUNNING experiment for duplicate configuration
    for running_exp in running_experiments:
        # Get variants for running experiment
        variants_result = await db.execute(
            select(ExperimentVariant).where(ExperimentVariant.experiment_id == running_exp.id)
        )
        variants = variants_result.scalars().all()
        running_service_ids = {v.service_id for v in variants}
        
        # Check if service IDs match
        if variant_service_ids != running_service_ids:
            continue
        
        # Check if task_type matches
        task_type_match = (
            (task_type is None and running_exp.task_type is None) or
            (task_type == [] and (running_exp.task_type is None or running_exp.task_type == [])) or
            (task_type and running_exp.task_type and set(task_type) == set(running_exp.task_type))
        )
        
        if not task_type_match:
            continue
        
        # Check if languages match
        languages_match = (
            (languages is None and running_exp.languages is None) or
            (languages == [] and (running_exp.languages is None or running_exp.languages == [])) or
            (languages and running_exp.languages and set(languages) == set(running_exp.languages))
        )
        
        if languages_match:
            return running_exp
    
    return None


async def create_experiment(payload, created_by: str = None) -> str:
    """
    Create a new A/B testing experiment.
    
    Args:
        payload: ExperimentCreateRequest object
        created_by: User ID who created the experiment
        
    Returns:
        Experiment ID (UUID as string)
    """
    from models.ab_testing import ExperimentCreateRequest
    
    db: AsyncSession = AppDatabase()
    try:
        # Validate that all service_ids exist and are published
        variant_service_ids = set()
        for variant in payload.variants:
            service_result = await db.execute(
                select(Service).where(Service.service_id == variant.service_id)
            )
            service = service_result.scalars().first()
            
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Service with ID '{variant.service_id}' not found"
                )
            
            if not service.is_published:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service '{variant.service_id}' must be published to be used in an experiment"
                )
            
            variant_service_ids.add(variant.service_id)
        
        # Create experiment (duplicates allowed, but only one can be RUNNING at a time)
        
        experiment = Experiment(
            name=payload.name,
            description=payload.description,
            status=ExperimentStatus.DRAFT,
            task_type=payload.task_type,
            languages=payload.languages,
            start_date=start_date,
            end_date=payload.end_date,
            created_by=created_by
        )
        
        db.add(experiment)
        await db.flush()  # Flush to get experiment.id
        
        # Create variants
        for variant_req in payload.variants:
            variant = ExperimentVariant(
                experiment_id=experiment.id,
                variant_name=variant_req.variant_name,
                service_id=variant_req.service_id,
                traffic_percentage=variant_req.traffic_percentage,
                description=variant_req.description
            )
            db.add(variant)
        
        await db.commit()
        await db.refresh(experiment)
        
        logger.info(f"Experiment '{payload.name}' (ID: {experiment.id}) created successfully.")
        return str(experiment.id)
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Error while creating experiment.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def get_experiment(experiment_id: str) -> Dict[str, Any]:
    """
    Get experiment details by ID.
    
    Args:
        experiment_id: Experiment UUID
        
    Returns:
        Dictionary with experiment details including variants
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            return None
        
        # Load variants
        variants_result = await db.execute(
            select(ExperimentVariant)
            .where(ExperimentVariant.experiment_id == experiment.id)
            .order_by(ExperimentVariant.traffic_percentage)
        )
        variants = variants_result.scalars().all()
        
        # Build response
        response = {
            "id": str(experiment.id),
            "name": experiment.name,
            "description": experiment.description,
            "status": experiment.status.value,
            "task_type": experiment.task_type,
            "languages": experiment.languages,
            "start_date": experiment.start_date.isoformat() if experiment.start_date else None,
            "end_date": experiment.end_date.isoformat() if experiment.end_date else None,
            "created_by": experiment.created_by,
            "updated_by": experiment.updated_by,
            "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
            "updated_at": experiment.updated_at.isoformat() if experiment.updated_at else None,
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
            "variants": [
                {
                    "id": str(v.id),
                    "variant_name": v.variant_name,
                    "service_id": v.service_id,
                    "traffic_percentage": v.traffic_percentage,
                    "description": v.description,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "updated_at": v.updated_at.isoformat() if v.updated_at else None,
                }
                for v in variants
            ]
        }
        
        return response
        
    except Exception as e:
        logger.exception(f"Error while fetching experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def list_experiments(
    status_filter: Optional[str] = None,
    task_type: Optional[str] = None,
    created_by: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all experiments with optional filters.
    
    Args:
        status_filter: Filter by experiment status
        task_type: Filter by task type
        created_by: Filter by creator
        
    Returns:
        List of experiment dictionaries
    """
    db: AsyncSession = AppDatabase()
    try:
        query = select(Experiment)
        
        if status_filter:
            try:
                status_enum = ExperimentStatus(status_filter.upper())
                query = query.where(Experiment.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}. Valid values: {[s.value for s in ExperimentStatus]}"
                )
        
        if task_type:
            query = query.where(Experiment.task_type.contains([task_type]))
        
        if created_by:
            query = query.where(Experiment.created_by == created_by)
        
        query = query.order_by(desc(Experiment.created_at))
        
        result = await db.execute(query)
        experiments = result.scalars().all()
        
        # Get variant counts for each experiment
        experiments_list = []
        for exp in experiments:
            variant_count_result = await db.execute(
                select(sql_func.count(ExperimentVariant.id))
                .where(ExperimentVariant.experiment_id == exp.id)
            )
            variant_count = variant_count_result.scalar() or 0
            
            experiments_list.append({
                "id": str(exp.id),
                "name": exp.name,
                "description": exp.description,
                "status": exp.status.value,
                "task_type": exp.task_type,
                "languages": exp.languages,
                "start_date": exp.start_date.isoformat() if exp.start_date else None,
                "end_date": exp.end_date.isoformat() if exp.end_date else None,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
                "updated_at": exp.updated_at.isoformat() if exp.updated_at else None,
                "variant_count": variant_count
            })
        
        return experiments_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while listing experiments.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list experiments: {str(e)}"
        ) from e
    finally:
        await db.close()


async def update_experiment(experiment_id: str, payload, updated_by: str = None) -> int:
    """
    Update an experiment.
    
    Args:
        experiment_id: Experiment UUID
        payload: ExperimentUpdateRequest object
        updated_by: User ID who updated the experiment
        
    Returns:
        Number of updated records (should be 1)
    """
    from models.ab_testing import ExperimentUpdateRequest
    
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        # Don't allow updates to RUNNING experiments (except status changes)
        if experiment.status == ExperimentStatus.RUNNING:
            if payload.variants is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot update variants of a running experiment. Stop it first."
                )
        
        # Update experiment fields
        if payload.name is not None:
            experiment.name = payload.name
        if payload.description is not None:
            experiment.description = payload.description
        if payload.task_type is not None:
            experiment.task_type = payload.task_type
            flag_modified(experiment, "task_type")
        if payload.languages is not None:
            experiment.languages = payload.languages
            flag_modified(experiment, "languages")
        if payload.start_date is not None:
            experiment.start_date = payload.start_date
        if payload.end_date is not None:
            experiment.end_date = payload.end_date
        if updated_by is not None:
            experiment.updated_by = updated_by
        
        # Update variants if provided
        if payload.variants is not None:
            # Validate services exist and are published
            for variant_req in payload.variants:
                service_result = await db.execute(
                    select(Service).where(Service.service_id == variant_req.service_id)
                )
                service = service_result.scalars().first()
                
                if not service:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Service with ID '{variant_req.service_id}' not found"
                    )
                
                if not service.is_published:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Service '{variant_req.service_id}' must be published"
                    )
            
            # Delete existing variants
            await db.execute(
                delete(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
            )
            
            # Create new variants
            for variant_req in payload.variants:
                variant = ExperimentVariant(
                    experiment_id=experiment.id,
                    variant_name=variant_req.variant_name,
                    service_id=variant_req.service_id,
                    traffic_percentage=variant_req.traffic_percentage,
                    description=variant_req.description
                )
                db.add(variant)
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} updated successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while updating experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def update_experiment_status(experiment_id: str, action: str, updated_by: str = None) -> int:
    """
    Update experiment status based on action.
    
    Args:
        experiment_id: Experiment UUID
        action: Action to perform ('start', 'stop', 'pause', 'resume', 'cancel')
        updated_by: User ID who performed the action
        
    Returns:
        Number of updated records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        action = action.lower()
        now = datetime.now()
        
        if action == "start":
            if experiment.status != ExperimentStatus.DRAFT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start experiment in '{experiment.status.value}' status. Only DRAFT experiments can be started."
                )
            
            # Verify at least 2 variants exist
            variant_count_result = await db.execute(
                select(sql_func.count(ExperimentVariant.id))
                .where(ExperimentVariant.experiment_id == experiment.id)
            )
            variant_count = variant_count_result.scalar() or 0
            
            if variant_count < 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least 2 variants are required to start an experiment"
                )
            
            # Check for duplicate RUNNING experiment with same configuration
            variants_result = await db.execute(
                select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
            )
            variants = variants_result.scalars().all()
            variant_service_ids = {v.service_id for v in variants}
            
            duplicate_exp = await _check_duplicate_running_experiment(
                db=db,
                experiment_id=experiment.id,
                variant_service_ids=variant_service_ids,
                task_type=experiment.task_type,
                languages=experiment.languages,
                start_date=experiment.start_date,
                end_date=experiment.end_date
            )
            
            if duplicate_exp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start experiment: Another experiment '{duplicate_exp.name}' (ID: {duplicate_exp.id}) is already RUNNING with the same configuration (same service IDs, task types, languages, and overlapping date range). Only one experiment with identical configuration can be RUNNING at a time."
                )
            
            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = now
            
        elif action == "stop":
            if experiment.status != ExperimentStatus.RUNNING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot stop experiment in '{experiment.status.value}' status. Only RUNNING experiments can be stopped."
                )
            
            experiment.status = ExperimentStatus.COMPLETED
            experiment.completed_at = now
            
        elif action == "pause":
            if experiment.status != ExperimentStatus.RUNNING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot pause experiment in '{experiment.status.value}' status. Only RUNNING experiments can be paused."
                )
            
            experiment.status = ExperimentStatus.PAUSED
            
        elif action == "resume":
            if experiment.status != ExperimentStatus.PAUSED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot resume experiment in '{experiment.status.value}' status. Only PAUSED experiments can be resumed."
                )
            
            # Check for duplicate RUNNING experiment with same configuration
            variants_result = await db.execute(
                select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
            )
            variants = variants_result.scalars().all()
            variant_service_ids = {v.service_id for v in variants}
            
            duplicate_exp = await _check_duplicate_running_experiment(
                db=db,
                experiment_id=experiment.id,
                variant_service_ids=variant_service_ids,
                task_type=experiment.task_type,
                languages=experiment.languages,
                start_date=experiment.start_date,
                end_date=experiment.end_date
            )
            
            if duplicate_exp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot resume experiment: Another experiment '{duplicate_exp.name}' (ID: {duplicate_exp.id}) is already RUNNING with the same configuration (same service IDs, task types, languages, and overlapping date range). Only one experiment with identical configuration can be RUNNING at a time."
                )
            
            experiment.status = ExperimentStatus.RUNNING
            
        elif action == "cancel":
            if experiment.status == ExperimentStatus.RUNNING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot cancel a RUNNING experiment. Stop it first."
                )
            
            experiment.status = ExperimentStatus.CANCELLED
            experiment.completed_at = now
            
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action '{action}'. Valid actions: start, stop, pause, resume, cancel"
            )
        
        if updated_by:
            experiment.updated_by = updated_by
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} status updated to {experiment.status.value} (action: {action}) by user {updated_by}.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while updating experiment status {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update experiment status: {str(e)}"
        ) from e
    finally:
        await db.close()


async def start_experiment(experiment_id: str, updated_by: str = None) -> int:
    """
    Start a DRAFT experiment by changing status to RUNNING.
    
    Args:
        experiment_id: Experiment UUID
        updated_by: User ID who started the experiment
        
    Returns:
        Number of updated records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        if experiment.status != ExperimentStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start experiment in '{experiment.status.value}' status. Only DRAFT experiments can be started."
            )
        
        # Verify at least 2 variants exist
        variant_count_result = await db.execute(
            select(sql_func.count(ExperimentVariant.id))
            .where(ExperimentVariant.experiment_id == experiment.id)
        )
        variant_count = variant_count_result.scalar() or 0
        
        if variant_count < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 variants are required to start an experiment"
            )
        
        # Update status
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now()
        if updated_by:
            experiment.updated_by = updated_by
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} started successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while starting experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def stop_experiment(experiment_id: str, updated_by: str = None) -> int:
    """
    Stop a RUNNING experiment by changing status to COMPLETED.
    
    Args:
        experiment_id: Experiment UUID
        updated_by: User ID who stopped the experiment
        
    Returns:
        Number of updated records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        if experiment.status != ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot stop experiment in '{experiment.status.value}' status. Only RUNNING experiments can be stopped."
            )
        
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now()
        if updated_by:
            experiment.updated_by = updated_by
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} stopped successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while stopping experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def pause_experiment(experiment_id: str, updated_by: str = None) -> int:
    """
    Pause a RUNNING experiment.
    
    Args:
        experiment_id: Experiment UUID
        updated_by: User ID who paused the experiment
        
    Returns:
        Number of updated records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        if experiment.status != ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot pause experiment in '{experiment.status.value}' status. Only RUNNING experiments can be paused."
            )
        
        experiment.status = ExperimentStatus.PAUSED
        if updated_by:
            experiment.updated_by = updated_by
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} paused successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while pausing experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def resume_experiment(experiment_id: str, updated_by: str = None) -> int:
    """
    Resume a PAUSED experiment.
    
    Args:
        experiment_id: Experiment UUID
        updated_by: User ID who resumed the experiment
        
    Returns:
        Number of updated records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        if experiment.status != ExperimentStatus.PAUSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resume experiment in '{experiment.status.value}' status. Only PAUSED experiments can be resumed."
            )
        
        experiment.status = ExperimentStatus.RUNNING
        if updated_by:
            experiment.updated_by = updated_by
        
        await db.commit()
        logger.info(f"Experiment {experiment_id} resumed successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while resuming experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def delete_experiment(experiment_id: str) -> int:
    """
    Delete an experiment (only if not RUNNING).
    
    Args:
        experiment_id: Experiment UUID
        
    Returns:
        Number of deleted records (should be 1)
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        experiment = result.scalars().first()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        if experiment.status == ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete a RUNNING experiment. Stop it first."
            )
        
        await db.execute(
            delete(Experiment).where(Experiment.id == UUID(experiment_id))
        )
        await db.commit()
        
        logger.info(f"Experiment {experiment_id} deleted successfully.")
        return 1
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error while deleting experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete experiment: {str(e)}"
        ) from e
    finally:
        await db.close()


async def select_experiment_variant(
    task_type: str,
    language: Optional[str] = None,
    request_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Select an experiment variant for a given request based on traffic distribution.
    This implements deterministic routing using consistent hashing.
    
    Args:
        task_type: Task type (e.g., 'asr', 'tts')
        language: Optional language code
        request_id: Optional request ID for consistent routing
        
    Returns:
        Dictionary with variant and service details, or None if no active experiment matches
    """
    db: AsyncSession = AppDatabase()
    try:
        # Find active experiments matching the criteria
        query = select(Experiment).where(
            Experiment.status == ExperimentStatus.RUNNING
        )
        
        # Filter by task type if experiment has task_type filter
        # If task_type is None or empty array, it matches all tasks
        # Otherwise, it must contain the requested task_type
        query = query.where(
            or_(
                Experiment.task_type.is_(None),
                Experiment.task_type == [],
                Experiment.task_type.contains([task_type])
            )
        )
        
        # Filter by language if provided and experiment has language filter
        if language:
            query = query.where(
                or_(
                    Experiment.languages.is_(None),
                    Experiment.languages == [],
                    Experiment.languages.contains([language])
                )
            )
        
        # Check date range
        now = datetime.now()
        query = query.where(
            (Experiment.start_date.is_(None)) | (Experiment.start_date <= now)
        )
        query = query.where(
            (Experiment.end_date.is_(None)) | (Experiment.end_date >= now)
        )
        
        result = await db.execute(query)
        experiments = result.scalars().all()
        
        if not experiments:
            return None
        
        # For now, use the first matching experiment (can be enhanced for multiple experiments)
        # In production, you might want to prioritize or combine experiments
        experiment = experiments[0]
        
        # Get variants
        variants_result = await db.execute(
            select(ExperimentVariant)
            .where(ExperimentVariant.experiment_id == experiment.id)
            .order_by(ExperimentVariant.traffic_percentage)
        )
        variants = variants_result.scalars().all()
        
        if not variants:
            return None
        
        # Deterministic variant selection using consistent hashing
        # Use request_id if provided, otherwise generate a hash from task_type + language
        hash_input = request_id if request_id else f"{task_type}:{language or 'none'}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        bucket = hash_value % 100  # 0-99 bucket
        
        # Select variant based on traffic distribution
        cumulative = 0
        selected_variant = None
        for variant in variants:
            cumulative += variant.traffic_percentage
            if bucket < cumulative:
                selected_variant = variant
                break
        
        if not selected_variant:
            # Fallback to last variant (shouldn't happen if percentages sum to 100)
            selected_variant = variants[-1]
        
        # Get service details
        service_result = await db.execute(
            select(Service).where(Service.service_id == selected_variant.service_id)
        )
        service = service_result.scalars().first()
        
        if not service or not service.is_published:
            logger.warning(f"Service {selected_variant.service_id} not found or not published")
            return None
        
        return {
            "experiment_id": str(experiment.id),
            "variant_id": str(selected_variant.id),
            "variant_name": selected_variant.variant_name,
            "service_id": service.service_id,
            "model_id": service.model_id,
            "model_version": service.model_version,
            "endpoint": service.endpoint,
            "api_key": service.api_key,
            "is_experiment": True
        }
        
    except Exception as e:
        logger.exception(f"Error while selecting experiment variant for task_type={task_type}, language={language}")
        # Don't fail the request, just return None (no experiment)
        return None
    finally:
        await db.close()

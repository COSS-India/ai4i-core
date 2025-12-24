from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select , delete , update, func as sql_func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import Dict, Any, List
import os

from models.db_models import Model , Service, VersionStatus
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

# Model versioning configuration
MAX_ACTIVE_VERSIONS_PER_MODEL = int(os.getenv("MAX_ACTIVE_VERSIONS_PER_MODEL", "5"))



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
      - Max active versions enforcement
      - Record creation
      - Commit / rollback

    """
    db: AsyncSession = AppDatabase()
    try:
        # Pre-check for duplicates: check if (model_id, version) combination already exists
        stmt = select(Model).where(
            Model.model_id == payload.modelId,
            Model.version == payload.version
        )
        result = await db.execute(stmt)
        existing = result.scalar()

        if existing:
            logger.warning(f"Duplicate model_id and version: {payload.modelId} v{payload.version}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model with ID {payload.modelId} and version {payload.version} already exists."
            )
        
        # Check max active versions if this version is being created as ACTIVE
        version_status = payload.versionStatus if hasattr(payload, 'versionStatus') and payload.versionStatus else VersionStatus.ACTIVE
        if version_status == VersionStatus.ACTIVE:
            # Count active versions for this model_id
            active_count_stmt = select(sql_func.count(Model.id)).where(
                Model.model_id == payload.modelId,
                Model.version_status == VersionStatus.ACTIVE
            )
            active_count_result = await db.execute(active_count_stmt)
            active_count = active_count_result.scalar() or 0
            
            if active_count >= MAX_ACTIVE_VERSIONS_PER_MODEL:
                logger.warning(
                    f"Max active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model {payload.modelId}. "
                    f"Current active versions: {active_count}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum number of active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model {payload.modelId}. "
                           f"Please deprecate an existing active version before creating a new one."
                )
        
        payload_dict = _json_safe(payload)

        now_epoch = int(time.time())

        payload_dict["submittedOn"] = now_epoch
        payload_dict["updatedOn"] = None  

        # Create new model record
        new_model = Model(
            model_id=payload_dict.get("modelId"),
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
        )

        db.add(new_model)
        await db.commit()
        await db.refresh(new_model)
        logger.info(f"Model {payload.modelId} v{payload.version} successfully saved to DB.")

        # Cache the model in Redis
        try:
            payload_dict = model_redis_safe_payload(payload_dict)
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
    Note: modelId and version are used as identifiers to identify which version to update.
        """

    if not payload.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Version is required to update a specific model version."
        )

    logger.info(f"Attempting to update model: {payload.modelId} v{payload.version}")

    request_dict = payload.model_dump(exclude_none=True)
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

        # Check max active versions if changing status to ACTIVE
        if "versionStatus" in request_dict and request_dict["versionStatus"] == VersionStatus.ACTIVE:
            if existing_model.version_status != VersionStatus.ACTIVE:
                # Count active versions for this model_id (excluding current version)
                active_count_stmt = select(sql_func.count(Model.id)).where(
                    Model.model_id == payload.modelId,
                    Model.version_status == VersionStatus.ACTIVE,
                    Model.version != payload.version  # Exclude current version
                )
                active_count_result = await db.execute(active_count_stmt)
                active_count = active_count_result.scalar() or 0
                
                if active_count >= MAX_ACTIVE_VERSIONS_PER_MODEL:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Maximum number of active versions ({MAX_ACTIVE_VERSIONS_PER_MODEL}) reached for model {payload.modelId}. "
                               f"Please deprecate an existing active version before activating this one."
                    )

        # 1. Update DB first
        postgres_data = {}

        for key, value in request_dict.items():
            if value is None:
                continue    # PATCH: skip null fields

            # Skip modelId and version (used only for filtering, not updated)
            if key in ("modelId", "version"):
                continue

            # Handle version_status update
            if key == "versionStatus":
                postgres_data["version_status"] = value
                postgres_data["version_status_updated_at"] = datetime.now()
            # Custom snake_case mapping
            elif key == "refUrl":
                postgres_data["ref_url"] = value
            elif key == "inferenceEndPoint":
                postgres_data["inference_endpoint"] = _json_safe(value)
            elif key in ("task", "languages", "domain", "benchmarks", "submitter"):
                postgres_data[key] = _json_safe(value)
            else:
                postgres_data[key] = value

        postgres_data["updated_on"] = now_epoch
        logger.info(f"Updating DB for model {payload.modelId} v{payload.version} with fields: {list(postgres_data.keys())}")
        logger.debug(f"DB update data: {postgres_data}")

        # 2. Repository update - filter by both model_id and version
        result = await update_by_filter(
            {"model_id": payload.modelId, "version": payload.version}, 
            postgres_data
        )
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
    except Exception as e:
        await db.rollback()
        logger.exception("Error deleting model from DB.")
        raise Exception("Delete failed due to internal DB error") from e
    finally:
        await db.close()



async def get_model_details(model_id: str, version: str = None) -> Dict[str, Any]:
    """
    Get model details by model_id. If version is provided, returns that specific version.
    If version is not provided, returns the first matching model.
    """
    db: AsyncSession = AppDatabase()
    try:
        query = select(Model).where(Model.model_id == model_id)
        if version:
            query = query.where(Model.version == version)
        
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
            "isPublished": model.is_published,
            "publishedAt": datetime.fromtimestamp(model.published_at).isoformat() if model.published_at else None,
            "unpublishedAt": datetime.fromtimestamp(model.unpublished_at).isoformat() if model.unpublished_at else None,
         }
     
    except Exception as e:
         logger.error(f"[DB] Error fetching model details: {str(e)}")
         raise
    finally:
         await db.close()
    

async def list_all_models(task_type: TaskTypeEnum | None) -> List[Dict[str, Any]]:
    """Fetch all model records from DB and convert to response format."""

    db: AsyncSession = AppDatabase()
    try:
        query = select(Model)
        if task_type:
            query = query.where(Model.task['type'].astext == task_type.value)

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
                "isPublished": data.get("is_published", {}),
                "publishedAt": datetime.fromtimestamp(data.get("published_at", None)).isoformat() if data.get("published_at", None) else None ,
                "unpublishedAt": datetime.fromtimestamp( data.get("unpublished_at", None)).isoformat() if  data.get("unpublished_at", None) else None,
            })

        return result
    except Exception as e:
        logger.error(f"[DB] Error fetching model list: {str(e)}")
        raise
    finally:
        await db.close()


async def publish_model(payload_modelId: str):
    """
    Publish a model by setting is_published to True and updating published_at timestamp.
    """
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Model).where(Model.model_id == payload_modelId)
        result = await db.execute(stmt)
        model = result.scalars().first()

        if not model:
            logger.warning(f"Model with ID {payload_modelId} not found for publish.")
            return 0

        now_epoch = int(time.time())

        await db.execute(
                update(Model)
                .where(Model.model_id == payload_modelId)
                .values(
                    is_published=True,
                    published_at=now_epoch,
                    unpublished_at=None
                )
            )

        await db.commit()
        logger.info(f"Model {payload_modelId} published successfully.")

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while publishing model.")
        raise Exception("Publish failed due to internal DB error") from e
    finally:
        await db.close()
    
async def unpublish_model(payload_modelId: str):
    """
    Unpublish a model by setting is_published to False and updating unpublished_at timestamp.
    """
    db: AsyncSession = AppDatabase()
    try:
        stmt = select(Model).where(Model.model_id == payload_modelId)
        result = await db.execute(stmt)
        model = result.scalars().first()

        if not model:
            logger.warning(f"Model with ID {payload_modelId} not found for unpublish.")
            return 0

        now_epoch = int(time.time())

        await db.execute(
                update(Model)
                .where(Model.model_id == payload_modelId)
                .values(
                    is_published=False,
                    unpublished_at=now_epoch
                )
            )

        await db.commit()
        logger.info(f"Model {payload_modelId} unpublished successfully.")

        return 1

    except Exception as e:
        await db.rollback()
        logger.exception("Error while unpublishing model.")
        raise Exception("Unpublish failed due to internal DB error") from e
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
        result = await db.execute(
            select(Model).where(
                Model.model_id == payload.modelId,
                Model.version == payload.modelVersion
            )
        )
        model_exists = result.scalars().first()
        if not model_exists:
            raise HTTPException(
                status_code=400,
                detail=f"Model with ID {payload.modelId} and version {payload.modelVersion} does not exist, cannot create service."
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
        )
        db.add(new_service)
        await db.commit()
        await db.refresh(new_service)
        logger.info(f"Service {payload.serviceId} successfully saved to DB.")


        # Cache the model in Redis
        try:
            cache_entry = ServiceCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Service {new_service.service_id} cached in Redis.")
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
            db_update["model_version"] = request_dict["modelVersion"]
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
        
        # Validate model exists - use modelVersion if provided, otherwise use existing service's model_version
        model_version_to_check = request_dict.get("modelVersion") or db_service.model_version
        result_model = await db.execute(
            select(Model).where(
                Model.model_id == request.modelId,
                Model.version == model_version_to_check
            )
        )
        model_exists = result_model.scalars().first()
        if not model_exists:
            raise HTTPException(
                status_code=400,
                detail=f"Model with ID {request.modelId} and version {model_version_to_check} does not exist, cannot update service."
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
                ModelCache.delete(service_id)
                logger.info(f"Cache deleted for modelId='{service_id}'")

        except Exception as cache_err:
            logger.warning(f"ModelCache delete failed for {uuid}: {cache_err}")


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



async def list_all_services(task_type: TaskTypeEnum | None) -> List[Dict[str, Any]]:
    """Fetch all service records from DB and convert to response format."""

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

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from models.db_models import Model
from db_connection import AppDatabase
from models.cache_models import ModelCache
from logger import logger
import json

from models.model_update import ModelUpdateRequest
from typing import Dict, Any, List
from sqlalchemy.orm.attributes import flag_modified
from uuid import UUID


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
    

def redis_safe_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
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
    

def save_model_to_db(payload: Model):
    """
    Save a new model entry to the database.
    Includes:
      - Duplicate model_id check
      - Record creation
      - Commit / rollback

    """

    db: Session = AppDatabase()
    try:
        # Pre-check for duplicates
        existing = db.query(Model).filter(Model.model_id == payload.modelId).first()
        if existing:
            logger.warning(f"Duplicate model_id: {payload.modelId}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model with ID {payload.modelId} already exists."
            )
        
        payload_dict = _json_safe(payload)

        # Create new model record
        new_model = Model(
            model_id=payload_dict["modelId"],
            version=payload_dict["version"],
            submitted_on=payload_dict["submittedOn"],
            updated_on=payload_dict["updatedOn"],
            name=payload_dict["name"],
            description=payload_dict["description"],
            ref_url=payload_dict["refUrl"],
            task=payload_dict["task"],
            languages=payload_dict["languages"],
            license=payload_dict["license"],
            domain=payload_dict["domain"],
            inference_endpoint=payload_dict["inferenceEndPoint"],
            benchmarks=payload_dict["benchmarks"],
            submitter=payload_dict["submitter"],
        )

        db.add(new_model)
        db.commit()
        db.refresh(new_model)
        logger.info(f"Model {payload.modelId} successfully saved to DB.")

        # Cache the model in Redis
        try:
            payload_dict = redis_safe_payload(payload_dict)
            cache_entry = ModelCache(**payload_dict)
            cache_entry.save()
            logger.info(f"Model {new_model.model_id} cached in Redis.")
        except Exception as ce:
            logger.warning(f"Could not cache model {new_model.model_id}: {ce}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error while saving model to DB.")
        raise Exception("Insert failed due to internal DB error") from e
    finally:
        # Always close session
        db.close()


def update_by_filter(filters: Dict[str, Any], data: Dict[str, Any]) -> int:
    db: Session = AppDatabase()
    try:
        query = db.query(Model)

        if not filters:
            raise ValueError("Filters required to update records.")

        # Apply filters
        for key, value in filters.items():
            if hasattr(Model, key):
                query = query.filter(getattr(Model, key) == value)
            else:
                raise ValueError(f"Invalid filter field: {key}")

        records = query.all()

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

        db.commit()
        return len(records)

    except Exception as e:
        db.rollback()
        logger.exception("Failed to update records.")
        raise ValueError(f"Failed to update records: {e}") from e

    finally:
        db.close()


def update_model(request: ModelUpdateRequest):

    logger.info(f"Attempting to update model: {request.modelId}")

    request_dict = request.model_dump(exclude_none=True)

    # 1. Check in cache (consistent behavior)
    try:
        cache = ModelCache.get(request.modelId)
    except Exception:
        logger.warning(f"Model {request.modelId} not found in cache")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in cache"
        )

    # 2. Patch cache (only simple fields)
    new_cache = cache.model_dump()

    model_fields = cache.__class__.model_fields

    for key, value in request_dict.items():
        if key in model_fields and value is not None:
            new_cache[key] = value

    # Convert to Redis-safe format before saving
    new_cache = redis_safe_payload(new_cache)

    # Save patched cache
    try:
        updated_cache = ModelCache(**new_cache)
        updated_cache.save()
        logger.info(f"Cache updated for model {request.modelId}")
    except Exception as ce:
        logger.warning(f"Failed to update cache for {request.modelId}: {ce}")

    # 3. DB Patch Logic (CamelCase → snake_case)
    postgres_data = {}

    for key, value in request_dict.items():
        if value is None:
            continue    # PATCH: skip null fields

        # Skip modelId (used only for filtering)
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

    logger.info(f"Updating DB for model {request.modelId} with fields: {list(postgres_data.keys())}")
    logger.debug(f"DB update data: {postgres_data}")

    # 4. Repository update
    result = update_by_filter({"model_id": request.modelId}, postgres_data)

    logger.info(f"Model {request.modelId} successfully updated.")

    return result





def delete_model_by_uuid(id_str: str) -> int:
    """Delete model by internal UUID (id)"""

    db: Session = AppDatabase()

    # Convert to UUID
    try:
        uuid = UUID(id_str)
    except ValueError:
        logger.warning(f"Invalid UUID provided for delete: {uuid}")
        return 0
    
    model = db.query(Model).filter(Model.id == uuid).first()

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


    result = (
        db.query(Model)
          .filter(Model.id == uuid)
          .delete()
    )

    db.commit()
    logger.info(f"DB: Model with ID {uuid} deleted successfully.")

    return result



def get_model_details(model_id: str) -> Dict[str, Any]:
     
    db: Session = AppDatabase()
    try:
        model = db.query(Model).where(Model.model_id == model_id).one()

        if not model:
             return None
        return {
             "modelId": model.model_id,
             "name": model.name,
             "description": model.description,
             "languages": model.languages or [],
             "domain": model.domain,
             "submitter": model.submitter,
             "license": model.license,
             "inferenceEndPoint": model.inference_endpoint,
             "source": "",  ## ask value for this field
             "task": model.task
         }
     
    except Exception as e:
         logger.error(f"[DB] Error fetching model details: {str(e)}")
         raise
    

def list_all_models() -> List[Dict[str, Any]]:
    """Fetch all model records from DB and convert to response format."""
    db: Session = AppDatabase()

    models = db.query(Model).all()

    result = []
    for item in models:
        # Convert SQLAlchemy model → dict
        data = item.__dict__.copy()
        data.pop("_sa_instance_state", None)

        # Build response object
        result.append({
            "modelId": str(data.get("model_id")),
            "name": data.get("name"),
            "description": data.get("description"),
            "languages": data.get("languages") or [],
            "domain": data.get("domain"),
            "submitter": data.get("submitter"),
            "license": data.get("license"),
            "inferenceEndPoint": data.get("inference_endpoint"),
            "source": data.get("ref_url"),
            "task": data.get("task", {})
        })

    return result


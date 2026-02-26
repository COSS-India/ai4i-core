"""
Database operations for SMR service.
Direct DB access functions to replace Model Management service calls.
"""
from sqlalchemy import select, and_, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from uuid import UUID

from models import Model, Service, TaskTypeEnum, VersionStatus
from db_connection import AppDatabase

try:
    from ai4icore_logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


async def get_model_details(model_id: str, version: str = None) -> Optional[Dict[str, Any]]:
    """
    Get model details by model_id. If version is provided, returns that specific version.
    If version is not provided, returns the latest ACTIVE version first, then falls back to
    latest DEPRECATED version if no ACTIVE versions exist.
    """
    db: AsyncSession = AppDatabase()
    try:
        query = select(Model).where(Model.model_id == model_id)
        if version:
            # Specific version requested
            query = query.where(Model.version == version)
        else:
            # No version specified - prioritize ACTIVE versions, then latest by submitted_on
            status_priority = case(
                (Model.version_status == VersionStatus.ACTIVE, 0),
                else_=1
            )
            query = query.order_by(
                status_priority,
                desc(Model.submitted_on)
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
        logger.error(f"[DB] Error fetching model details: {str(e)}", exc_info=True)
        raise
    finally:
        try:
            await db.close()
        except Exception:
            pass


async def list_all_services(
    task_type: Optional[str] = None, 
    is_published: bool = None,
    created_by: str = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch all service records from DB and convert to response format.
    
    Args:
        task_type: Optional filter by task type (asr, nmt, tts, etc.) as string
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
            # Convert string to TaskTypeEnum if valid
            try:
                task_type_enum = TaskTypeEnum(task_type.lower())
                query = query.where(Model.task['type'].astext == task_type_enum.value)
            except ValueError:
                logger.warning(f"Invalid task_type: {task_type}")
                return None
        
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
            logger.error(f"[DB] Failed to fetch services: {str(e)}", exc_info=True)
            raise

        if not rows:
            task_type_str = task_type if task_type else "all"
            logger.info(f"[DB] No services found for task_type={task_type_str}")
            return None

        services_list = []

        for service, model in rows:
            if not model:
                logger.error(
                    f"[DB] Failed to get model details from db for service {service.service_id}"
                )
                continue
            
            # Get policy - access directly from service object
            service_policy = None
            try:
                if hasattr(service, 'policy') and service.policy is not None:
                    service_policy = dict(service.policy) if not isinstance(service.policy, dict) else service.policy
                else:
                    service_policy = None
            except Exception as e:
                logger.warning(f"[DB] Error accessing policy for {service.service_id}: {e}")
                service_policy = None
            
            # Convert languages to List[dict] format
            languages_raw = getattr(model, "languages", []) if model else []
            languages = []
            if languages_raw:
                for lang in languages_raw:
                    if isinstance(lang, dict):
                        languages.append(lang)
                    elif isinstance(lang, str):
                        languages.append({"sourceLanguage": lang})
                    else:
                        continue
            
            # Convert task dict
            task_dict = getattr(model, "task", {}) if model else {}
            
            # Ensure required string fields are not None
            service_description = getattr(service, "service_description", None) or ""
            hardware_description = getattr(service, "hardware_description", None) or ""
            published_on = getattr(service, "published_on", None) or 0
            
            service_dict = {
                "serviceId": str(service.service_id),
                "uuid": str(service.id),
                "name": service.name,
                "serviceDescription": service_description,
                "hardwareDescription": hardware_description,
                "publishedOn": published_on,
                "modelId": service.model_id,
                "endpoint": getattr(service, "endpoint", None),
                "healthStatus": getattr(service, "health_status", None),
                "benchmarks": getattr(service, "benchmarks", None),
                "policy": service_policy,
                "isPublished": getattr(service, "is_published", False),
                "publishedAt": None,  # Will be converted if needed
                "unpublishedAt": None,  # Will be converted if needed
                "createdBy": getattr(service, "created_by", None),
                "updatedBy": getattr(service, "updated_by", None),
                "task": task_dict,
                "languages": languages,
                "modelVersion": service.model_version,
                "versionStatus": model.version_status.value if model and model.version_status else None
            }
            
            # Convert timestamps if they exist
            if service.published_at:
                from datetime import datetime
                service_dict["publishedAt"] = datetime.fromtimestamp(service.published_at).isoformat()
            if service.unpublished_at:
                from datetime import datetime
                service_dict["unpublishedAt"] = datetime.fromtimestamp(service.unpublished_at).isoformat()
            
            services_list.append(service_dict)

        return services_list if services_list else None

    except Exception as e:
        logger.error(f"[DB] Error fetching service list: {str(e)}", exc_info=True)
        raise
    finally:
        try:
            await db.close()
        except Exception:
            pass


async def list_services_with_policies(task_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all services with their policies, optionally filtered by task_type.
    
    Args:
        task_type: Optional filter by task type (asr, nmt, tts, etc.) as string
        
    Returns:
        List of dictionaries with service_id and policy for each service
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
            try:
                task_type_enum = TaskTypeEnum(task_type.lower())
                query = query.where(Model.task['type'].astext == task_type_enum.value)
            except ValueError:
                logger.warning(f"Invalid task_type: {task_type}")
                return []
        
        # Order by service_id for consistent results
        query = query.order_by(Service.service_id)
        
        result = await db.execute(query)
        rows = result.all()
        
        services_with_policies = []
        for service, model in rows:
            policy_dict = dict(service.policy) if service.policy else None
            services_with_policies.append({
                "serviceId": service.service_id,
                "policy": policy_dict
            })
        
        return services_with_policies
        
    except Exception as e:
        logger.exception("Error while listing services with policies")
        return []
    finally:
        try:
            await db.close()
        except Exception:
            pass

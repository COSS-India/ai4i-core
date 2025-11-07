from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.config_models import (
    ConfigurationCreate,
    ConfigurationListResponse,
    ConfigurationQuery,
    ConfigurationResponse,
    ConfigurationUpdate,
)
from repositories.config_repository import ConfigRepository
from services.config_service import ConfigurationService
import os


router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])


def get_config_service() -> ConfigurationService:
    import main as app_main  # type: ignore
    repo = ConfigRepository(app_main.db_session)
    topic = os.getenv('KAFKA_TOPIC_CONFIG_UPDATES', 'config-updates')
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Using Kafka topic for config updates: {topic}")
    return ConfigurationService(
        repo,
        app_main.redis_client,
        app_main.kafka_producer,
        kafka_topic=topic,
        vault_client=getattr(app_main, 'vault_client', None),
        cache_ttl=300
    )


@router.post("/", response_model=ConfigurationResponse, status_code=201)
async def create_configuration(data: ConfigurationCreate, service: ConfigurationService = Depends(get_config_service)):
    return await service.create_configuration(data)


@router.get("/{key}", response_model=ConfigurationResponse)
async def get_configuration(
    key: str, 
    environment: str = Query(...), 
    service_name: str = Query(...),
    mask: bool = Query(False, description="Mask encrypted values in response"),
    service: ConfigurationService = Depends(get_config_service)
):
    result = await service.get_configuration(key, environment, service_name)
    if not result:
        raise HTTPException(status_code=404, detail="Configuration not found")
    # Mask encrypted values if requested
    if mask and result.is_encrypted:
        result.mask_value = True
    return result


@router.get("/", response_model=ConfigurationListResponse)
async def get_configurations(
    environment: Optional[str] = None,
    service_name: Optional[str] = None,
    keys: Optional[List[str]] = Query(default=None),
    limit: int = 50,
    offset: int = 0,
    mask: bool = Query(False, description="Mask encrypted values in response"),
    service: ConfigurationService = Depends(get_config_service),
):
    items, total = await service.get_configurations(environment, service_name, keys, limit, offset)
    # Mask encrypted values if requested
    if mask:
        for item in items:
            if item.is_encrypted:
                item.mask_value = True
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.put("/{key}", response_model=ConfigurationResponse)
async def update_configuration(key: str, data: ConfigurationUpdate, environment: str = Query(...), service_name: str = Query(...), service: ConfigurationService = Depends(get_config_service)):
    result = await service.update_configuration(key, environment, service_name, data.value, data.is_encrypted)
    if not result:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return result


@router.delete("/{key}", status_code=204)
async def delete_configuration(key: str, environment: str = Query(...), service_name: str = Query(...), service: ConfigurationService = Depends(get_config_service)):
    ok = await service.delete_configuration(key, environment, service_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return


@router.get("/{key}/history")
async def configuration_history(key: str, environment: str = Query(...), service_name: str = Query(...), service: ConfigurationService = Depends(get_config_service)):
    cfg = await service.get_configuration(key, environment, service_name)
    if not cfg:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return await service.get_configuration_history(cfg.id)


@router.post("/bulk")
async def bulk_get_configurations(environment: str, service_name: str, keys: List[str], service: ConfigurationService = Depends(get_config_service)):
    return await service.bulk_get_configurations(environment, service_name, keys)



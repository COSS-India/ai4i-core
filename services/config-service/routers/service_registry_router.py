from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from models.service_registry_models import ServiceInstance, ServiceRegistration
from repositories.service_registry_repository import ServiceRegistryRepository
from services.service_registry_service import ServiceRegistryService


router = APIRouter(prefix="/api/v1/registry", tags=["Service Registry"])


def get_registry_service() -> ServiceRegistryService:
    import main as app_main  # type: ignore
    repo = ServiceRegistryRepository(app_main.db_session)
    return ServiceRegistryService(app_main.registry_client, repo, app_main.redis_client, cache_ttl=60)


@router.post("/register", status_code=201)
async def register_service(payload: ServiceRegistration, service: ServiceRegistryService = Depends(get_registry_service)):
    instance_id = await service.register_service(payload.service_name, payload.service_url, payload.health_check_url, payload.service_metadata or {})
    return {"instance_id": instance_id}


@router.post("/deregister")
async def deregister_service(service_name: str, instance_id: str, service: ServiceRegistryService = Depends(get_registry_service)):
    await service.deregister_service(service_name, instance_id)
    return {"status": "ok"}


@router.get("/services", response_model=List[ServiceInstance])
async def list_services(service: ServiceRegistryService = Depends(get_registry_service)):
    return await service.list_all_services()


@router.get("/services/{service_name}", response_model=List[ServiceInstance])
async def service_instances(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    return await service.get_service_instances(service_name)


@router.get("/services/{service_name}/url")
async def service_url(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    url = await service.get_service_url(service_name)
    if not url:
        raise HTTPException(status_code=404, detail="No healthy instances found")
    return {"url": url}


@router.post("/services/{service_name}/health")
async def trigger_health_check(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    status = await service.perform_health_check(service_name)
    return {"status": status.value}


@router.get("/discover/{service_name}", response_model=List[ServiceInstance])
async def discover(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    return await service.get_service_instances(service_name)



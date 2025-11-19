from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from models.service_registry_models import ServiceInstance, ServiceRegistration
from repositories.service_registry_repository import ServiceRegistryRepository
from services.service_registry_service import ServiceRegistryService


router = APIRouter(prefix="/api/v1/registry", tags=["Service Registry"])


def get_registry_service() -> ServiceRegistryService:
    import main as app_main  # type: ignore
    repo = ServiceRegistryRepository(app_main.db_session)
    return ServiceRegistryService(
        app_main.registry_client,
        repo,
        app_main.redis_client,
        cache_ttl=60,
        health_monitor=app_main.health_monitor_service,
    )


@router.post("/register", status_code=201)
async def register_service(payload: ServiceRegistration, service: ServiceRegistryService = Depends(get_registry_service)):
    instance_id = await service.register_service(payload.service_name, payload.service_url, payload.health_check_url, payload.service_metadata or {})
    return {"instance_id": instance_id}


@router.post("/deregister")
async def deregister_service(service_name: str, instance_id: str, service: ServiceRegistryService = Depends(get_registry_service)):
    await service.deregister_service(service_name, instance_id)
    return {"status": "ok"}


@router.get("/services", response_model=List[ServiceInstance], response_model_exclude_none=True)
async def list_services(service: ServiceRegistryService = Depends(get_registry_service)):
    items = await service.list_all_services()
    # Enterprise-friendly response: omit fields that are not available (e.g., instance_id when not tracked in DB)
    return [i.model_dump(exclude_none=True) for i in items]


@router.get("/services/{service_name}", response_model=List[ServiceInstance], response_model_exclude_none=True)
async def service_instances(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    items = await service.get_service_instances(service_name)
    # Hide nulls if any instance fields are unavailable
    return [i.model_dump(exclude_none=True) for i in items]


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


@router.post("/services/{service_name}/health/detailed")
async def trigger_detailed_health_check(
    service_name: str,
    service: ServiceRegistryService = Depends(get_registry_service),
):
    """Trigger detailed health check with aggregated results"""
    try:
        aggregated_result = await service.perform_health_check_with_details(service_name)
        return {
            "service_name": aggregated_result.service_name,
            "overall_status": aggregated_result.overall_status.value,
            "total_instances": aggregated_result.total_instances,
            "healthy_instances": aggregated_result.healthy_instances,
            "unhealthy_instances": aggregated_result.unhealthy_instances,
            "check_results": [
                {
                    "endpoint_url": r.endpoint_url,
                    "is_healthy": r.is_healthy,
                    "response_time_ms": r.response_time_ms,
                    "status_code": r.status_code,
                    "error_message": r.error_message,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in aggregated_result.check_results
            ],
            "timestamp": aggregated_result.timestamp.isoformat() if aggregated_result.timestamp else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/discover/{service_name}", response_model=List[ServiceInstance])
async def discover(service_name: str, service: ServiceRegistryService = Depends(get_registry_service)):
    return await service.get_service_instances(service_name)



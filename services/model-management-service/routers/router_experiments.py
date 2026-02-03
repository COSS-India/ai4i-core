"""
API Router for A/B Experiments.
Provides endpoints to create, manage, and resolve experiments.
"""
from fastapi import APIRouter, HTTPException, status, Query, Request, Depends
from typing import List, Optional

from models.experiment_models import (
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    ExperimentResponse,
    ExperimentSummary,
    VariantResolution,
    ExperimentStartStopResponse,
    ExperimentStatus,
)
from experiment_operations import (
    create_experiment,
    get_experiment,
    get_experiment_by_name,
    list_experiments,
    update_experiment,
    start_experiment,
    stop_experiment,
    delete_experiment,
    resolve_variant,
)
from middleware.auth_provider import AuthProvider
from logger import logger


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user_id from request state (set by AuthProvider or Kong) as string."""
    user_id = getattr(request.state, 'user_id', None)
    return str(user_id) if user_id is not None else None


router_experiments = APIRouter(
    prefix="/experiments",
    tags=["A/B Experiments"],
    dependencies=[Depends(AuthProvider)]
)


# ---- CRUD Endpoints ----

@router_experiments.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_experiment_endpoint(
    payload: ExperimentCreateRequest,
    request: Request
):
    """
    Create a new A/B experiment.
    
    The experiment starts in DRAFT status. Use POST /experiments/{id}/start to activate it.
    Only one experiment can be RUNNING per task_type at a time.
    """
    try:
        user_id = get_user_id_from_request(request)
        experiment_id = await create_experiment(payload, created_by=user_id)
        logger.info(f"Experiment '{payload.name}' created by user {user_id}")
        return {
            "id": experiment_id,
            "name": payload.name,
            "message": f"Experiment '{payload.name}' created successfully. Use POST /experiments/{experiment_id}/start to activate."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating experiment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to create experiment"}
        )


@router_experiments.get("", response_model=List[ExperimentResponse])
async def list_experiments_endpoint(
    task_type: Optional[str] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (DRAFT, RUNNING, STOPPED)")
):
    """
    List all A/B experiments with optional filters.
    """
    try:
        # Parse status filter
        status_enum = None
        if status_filter:
            try:
                status_enum = ExperimentStatus(status_filter.upper())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: DRAFT, RUNNING, STOPPED"
                )
        
        experiments = await list_experiments(task_type=task_type, status_filter=status_enum)
        return experiments
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing experiments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to list experiments"}
        )


@router_experiments.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment_endpoint(experiment_id: str):
    """
    Get experiment details by ID.
    """
    try:
        experiment = await get_experiment(experiment_id)
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found"
            )
        return experiment
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to fetch experiment"}
        )


@router_experiments.patch("/{experiment_id}", response_model=dict)
async def update_experiment_endpoint(
    experiment_id: str,
    payload: ExperimentUpdateRequest,
    request: Request
):
    """
    Update experiment settings.
    
    Note: You can update treatment_percentage even while the experiment is running.
    This allows gradual rollout (e.g., start at 10%, increase to 50%, then 100%).
    """
    try:
        user_id = get_user_id_from_request(request)
        await update_experiment(experiment_id, payload, updated_by=user_id)
        return {"message": f"Experiment '{experiment_id}' updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to update experiment"}
        )


@router_experiments.delete("/{experiment_id}", response_model=dict)
async def delete_experiment_endpoint(experiment_id: str):
    """
    Delete an experiment.
    
    Only DRAFT or STOPPED experiments can be deleted.
    Running experiments must be stopped first.
    """
    try:
        await delete_experiment(experiment_id)
        return {"message": f"Experiment '{experiment_id}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to delete experiment"}
        )


# ---- Start/Stop Endpoints ----

@router_experiments.post("/{experiment_id}/start", response_model=ExperimentStartStopResponse)
async def start_experiment_endpoint(experiment_id: str, request: Request):
    """
    Start an experiment (activate traffic splitting).
    
    - Experiment must be in DRAFT status
    - Only one experiment can be RUNNING per task_type
    - Use PATCH /experiments/{id} to adjust treatment_percentage after starting
    """
    try:
        user_id = get_user_id_from_request(request)
        result = await start_experiment(experiment_id, updated_by=user_id)
        return ExperimentStartStopResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to start experiment"}
        )


@router_experiments.post("/{experiment_id}/stop", response_model=ExperimentStartStopResponse)
async def stop_experiment_endpoint(experiment_id: str, request: Request):
    """
    Stop an experiment (disable traffic splitting).
    
    After stopping, all traffic will use default routing.
    Stopped experiments cannot be restarted - create a new experiment instead.
    """
    try:
        user_id = get_user_id_from_request(request)
        result = await stop_experiment(experiment_id, updated_by=user_id)
        return ExperimentStartStopResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error stopping experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"kind": "DBError", "message": "Failed to stop experiment"}
        )


# ---- Variant Resolution Endpoint (For Inference Services) ----

@router_experiments.get("/resolve/variant", response_model=VariantResolution)
async def resolve_variant_endpoint(
    task_type: str = Query(..., description="Task type: asr, nmt, tts, etc."),
    user_id: Optional[str] = Query(None, description="User ID for sticky assignment"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID for sticky assignment"),
    request_id: Optional[str] = Query(None, description="Request ID (fallback for sticky assignment)")
):
    """
    Resolve which service variant to use for a request.
    
    **This endpoint is called by inference services** (ASR, NMT, TTS, etc.) 
    before routing a request to determine which model/service to use.
    
    Returns:
    - `service_id`: The service to route to (empty string if no experiment)
    - `variant`: "control", "treatment", or "default" (no experiment)
    - `experiment_name`: Name of the active experiment (if any)
    - `experiment_id`: ID of the active experiment (if any)
    
    **Sticky Assignment:**
    - Same user_id always gets the same variant for the same experiment
    - If user_id is not provided, falls back to tenant_id, then request_id
    - This ensures consistent user experience during the experiment
    """
    try:
        # Note: We don't require auth for this endpoint as it's called internally
        # by other services. The calling service handles auth.
        result = await resolve_variant(
            task_type=task_type,
            user_id=user_id,
            tenant_id=tenant_id,
            request_id=request_id
        )
        return result
    except Exception as e:
        logger.exception(f"Error resolving variant for task_type={task_type}: {e}")
        # Return default on error (fail-safe)
        return VariantResolution(
            service_id="",
            variant="default",
            experiment_name=None,
            experiment_id=None
        )

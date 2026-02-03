from fastapi import HTTPException, status, APIRouter, Depends, Request, Query
from typing import Optional, List
from models.ab_testing import (
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    ExperimentStatusUpdateRequest,
    ExperimentResponse,
    ExperimentListResponse,
    ExperimentVariantSelectionRequest,
    ExperimentVariantSelectionResponse
)
from db_operations import (
    create_experiment,
    get_experiment,
    list_experiments,
    update_experiment,
    update_experiment_status,
    delete_experiment,
    select_experiment_variant
)
from middleware.auth_provider import AuthProvider
from logger import logger


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user_id from request state (set by AuthProvider or Kong) as string."""
    user_id = getattr(request.state, 'user_id', None)
    return str(user_id) if user_id is not None else None


router_experiments = APIRouter(
    prefix="/experiments",
    tags=["A/B Testing"],
    dependencies=[Depends(AuthProvider)]
)


@router_experiments.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment_endpoint(payload: ExperimentCreateRequest, request: Request):
    """
    Create a new A/B testing experiment.
    
    Requires at least 2 variants with traffic percentages summing to 100.
    """
    try:
        user_id = get_user_id_from_request(request)
        experiment_id = await create_experiment(payload, created_by=user_id)
        
        # Fetch and return the created experiment
        experiment_data = await get_experiment(experiment_id)
        if not experiment_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created experiment"
            )
        
        logger.info(f"Experiment '{payload.name}' (ID: {experiment_id}) created successfully by user {user_id}.")
        return experiment_data
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error creating experiment: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Error while creating experiment.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create experiment: {str(e)}"
        )


@router_experiments.get("", response_model=List[ExperimentListResponse])
async def list_experiments_endpoint(
    status: Optional[str] = Query(None, description="Filter by experiment status"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    created_by: Optional[str] = Query(None, description="Filter by creator user ID")
):
    """
    List all experiments with optional filters.
    """
    try:
        experiments = await list_experiments(
            status_filter=status,
            task_type=task_type,
            created_by=created_by
        )
        return experiments
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while listing experiments.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list experiments: {str(e)}"
        )


@router_experiments.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment_endpoint(experiment_id: str):
    """
    Get experiment details by ID.
    """
    try:
        experiment_data = await get_experiment(experiment_id)
        
        if not experiment_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        return experiment_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error while fetching experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch experiment: {str(e)}"
        )


@router_experiments.patch("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment_endpoint(
    experiment_id: str,
    payload: ExperimentUpdateRequest,
    request: Request
):
    """
    Update an experiment.
    
    Note: Cannot update variants of a RUNNING experiment.
    """
    try:
        user_id = get_user_id_from_request(request)
        result = await update_experiment(experiment_id, payload, updated_by=user_id)
        
        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        # Fetch and return updated experiment
        experiment_data = await get_experiment(experiment_id)
        logger.info(f"Experiment {experiment_id} updated successfully by user {user_id}.")
        return experiment_data
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating experiment: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error while updating experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update experiment: {str(e)}"
        )


@router_experiments.post("/{experiment_id}/status", response_model=ExperimentResponse)
async def update_experiment_status_endpoint(
    experiment_id: str,
    payload: ExperimentStatusUpdateRequest,
    request: Request
):
    """
    Update experiment status by action.
    
    Actions:
    - 'start': Start a DRAFT experiment (changes to RUNNING)
    - 'stop': Stop a RUNNING experiment (changes to COMPLETED)
    - 'pause': Pause a RUNNING experiment (changes to PAUSED)
    - 'resume': Resume a PAUSED experiment (changes to RUNNING)
    - 'cancel': Cancel a non-RUNNING experiment (changes to CANCELLED)
    """
    try:
        user_id = get_user_id_from_request(request)
        result = await update_experiment_status(experiment_id, payload.action, updated_by=user_id)
        
        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        experiment_data = await get_experiment(experiment_id)
        logger.info(f"Experiment {experiment_id} status updated (action: {payload.action}) by user {user_id}.")
        return experiment_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error while updating experiment status {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update experiment status: {str(e)}"
        )


@router_experiments.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment_endpoint(experiment_id: str):
    """
    Delete an experiment.
    
    Note: Cannot delete a RUNNING experiment. Stop it first.
    """
    try:
        result = await delete_experiment(experiment_id)
        
        if result == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment with ID '{experiment_id}' not found"
            )
        
        logger.info(f"Experiment {experiment_id} deleted successfully.")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error while deleting experiment {experiment_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete experiment: {str(e)}"
        )


# Public endpoint for variant selection (used by services/gateway)
router_experiments_public = APIRouter(
    prefix="/experiments",
    tags=["A/B Testing"],
    # No AuthProvider dependency - this is called internally
)


@router_experiments_public.post("/select-variant", response_model=ExperimentVariantSelectionResponse)
async def select_variant_endpoint(payload: ExperimentVariantSelectionRequest):
    """
    Select an experiment variant for a given request.
    
    This endpoint is used by the API gateway or services to determine
    which model/service variant to route a request to.
    
    Returns None if no active experiment matches the criteria.
    """
    try:
        variant_data = await select_experiment_variant(
            task_type=payload.task_type,
            language=payload.language,
            request_id=payload.request_id
        )
        
        if not variant_data:
            return ExperimentVariantSelectionResponse(is_experiment=False)
        
        return ExperimentVariantSelectionResponse(
            experiment_id=variant_data.get("experiment_id"),
            variant_id=variant_data.get("variant_id"),
            variant_name=variant_data.get("variant_name"),
            service_id=variant_data.get("service_id"),
            model_id=variant_data.get("model_id"),
            model_version=variant_data.get("model_version"),
            endpoint=variant_data.get("endpoint"),
            api_key=variant_data.get("api_key"),
            is_experiment=True
        )
        
    except Exception as e:
        logger.exception("Error while selecting experiment variant.")
        # Return no experiment rather than failing
        return ExperimentVariantSelectionResponse(is_experiment=False)

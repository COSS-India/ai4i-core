"""
Database operations for A/B experiments.
Handles CRUD operations and variant resolution logic.
"""
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import ABExperiment, ExperimentStatus, Service
from models.experiment_models import (
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    ExperimentResponse,
    VariantResolution,
)
from db_connection import AppDatabase
from logger import logger

# Redis cache TTL for experiment lookups (in seconds)
EXPERIMENT_CACHE_TTL = 60


def _compute_bucket(experiment_id: str, assignment_key: str) -> int:
    """
    Compute a deterministic bucket (0-99) for consistent user→variant assignment.
    Same user always gets the same bucket for the same experiment.
    """
    hash_input = f"{experiment_id}:{assignment_key}"
    hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    return hash_val % 100


# ---- Create ----

async def create_experiment(payload: ExperimentCreateRequest, created_by: Optional[str] = None) -> str:
    """
    Create a new A/B experiment (starts in DRAFT status).
    
    Args:
        payload: Experiment creation request
        created_by: User ID who created this experiment
        
    Returns:
        The UUID of the created experiment
    """
    db: AsyncSession = AppDatabase()
    try:
        # Check if experiment name already exists
        existing = await db.execute(
            select(ABExperiment).where(ABExperiment.name == payload.name)
        )
        if existing.scalar():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Experiment with name '{payload.name}' already exists"
            )
        
        # Validate that both services exist
        for service_id, label in [
            (payload.control_service_id, "control"),
            (payload.treatment_service_id, "treatment")
        ]:
            service_exists = await db.execute(
                select(Service.service_id).where(Service.service_id == service_id)
            )
            if not service_exists.scalar():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{label.capitalize()} service '{service_id}' not found"
                )
        
        # Create experiment
        experiment = ABExperiment(
            name=payload.name,
            description=payload.description,
            task_type=payload.task_type,
            control_service_id=payload.control_service_id,
            treatment_service_id=payload.treatment_service_id,
            treatment_percentage=payload.treatment_percentage,
            status=ExperimentStatus.DRAFT,
            created_by=created_by,
        )
        
        db.add(experiment)
        await db.commit()
        await db.refresh(experiment)
        
        logger.info(f"Created experiment '{payload.name}' (ID: {experiment.id}) for task_type={payload.task_type}")
        return str(experiment.id)
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error creating experiment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create experiment"
        )
    finally:
        await db.close()


# ---- Read ----

async def get_experiment(experiment_id: str) -> Optional[Dict[str, Any]]:
    """Get experiment by ID"""
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.id == experiment_id)
        )
        experiment = result.scalar()
        
        if not experiment:
            return None
        
        return _experiment_to_dict(experiment)
    except Exception as e:
        logger.exception(f"Error fetching experiment {experiment_id}: {e}")
        raise
    finally:
        await db.close()


async def get_experiment_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get experiment by name"""
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.name == name)
        )
        experiment = result.scalar()
        
        if not experiment:
            return None
        
        return _experiment_to_dict(experiment)
    except Exception as e:
        logger.exception(f"Error fetching experiment by name '{name}': {e}")
        raise
    finally:
        await db.close()


async def list_experiments(
    task_type: Optional[str] = None,
    status_filter: Optional[ExperimentStatus] = None
) -> List[Dict[str, Any]]:
    """List all experiments with optional filters"""
    db: AsyncSession = AppDatabase()
    try:
        query = select(ABExperiment).order_by(ABExperiment.created_at.desc())
        
        if task_type:
            query = query.where(ABExperiment.task_type == task_type.lower())
        
        if status_filter:
            query = query.where(ABExperiment.status == status_filter)
        
        result = await db.execute(query)
        experiments = result.scalars().all()
        
        return [_experiment_to_dict(exp) for exp in experiments]
    except Exception as e:
        logger.exception(f"Error listing experiments: {e}")
        raise
    finally:
        await db.close()


async def get_active_experiment_for_task(task_type: str) -> Optional[ABExperiment]:
    """
    Get the active (RUNNING) experiment for a task type.
    Only one experiment can be RUNNING per task_type.
    """
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(ABExperiment).where(
                ABExperiment.task_type == task_type.lower(),
                ABExperiment.status == ExperimentStatus.RUNNING
            )
        )
        return result.scalar()
    except Exception as e:
        logger.exception(f"Error getting active experiment for task {task_type}: {e}")
        raise
    finally:
        await db.close()


# ---- Update ----

async def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdateRequest,
    updated_by: Optional[str] = None
) -> bool:
    """Update experiment (limited fields can be updated)"""
    db: AsyncSession = AppDatabase()
    try:
        # Get existing experiment
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.id == experiment_id)
        )
        experiment = result.scalar()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found"
            )
        
        # Build update dict
        update_data = {"updated_by": updated_by}
        
        if payload.description is not None:
            update_data["description"] = payload.description
        
        if payload.treatment_percentage is not None:
            update_data["treatment_percentage"] = payload.treatment_percentage
            logger.info(f"Experiment {experiment_id} treatment_percentage updated to {payload.treatment_percentage}%")
        
        await db.execute(
            update(ABExperiment)
            .where(ABExperiment.id == experiment_id)
            .values(**update_data)
        )
        await db.commit()
        
        return True
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error updating experiment {experiment_id}: {e}")
        raise
    finally:
        await db.close()


# ---- Start/Stop ----

async def start_experiment(experiment_id: str, updated_by: Optional[str] = None) -> Dict[str, Any]:
    """
    Start an experiment (change status from DRAFT to RUNNING).
    Only one experiment can be RUNNING per task_type.
    """
    db: AsyncSession = AppDatabase()
    try:
        # Get experiment
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.id == experiment_id)
        )
        experiment = result.scalar()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found"
            )
        
        if experiment.status == ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Experiment is already running"
            )
        
        if experiment.status == ExperimentStatus.STOPPED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot restart a stopped experiment. Create a new experiment instead."
            )
        
        # Check if another experiment is already running for this task_type
        existing_running = await db.execute(
            select(ABExperiment).where(
                ABExperiment.task_type == experiment.task_type,
                ABExperiment.status == ExperimentStatus.RUNNING,
                ABExperiment.id != experiment_id
            )
        )
        if existing_running.scalar():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another experiment is already running for task_type '{experiment.task_type}'. Stop it first."
            )
        
        # Start the experiment
        await db.execute(
            update(ABExperiment)
            .where(ABExperiment.id == experiment_id)
            .values(
                status=ExperimentStatus.RUNNING,
                started_at=datetime.utcnow(),
                updated_by=updated_by
            )
        )
        await db.commit()
        
        logger.info(f"Started experiment '{experiment.name}' (ID: {experiment_id}) for task_type={experiment.task_type}")
        
        return {
            "id": str(experiment.id),
            "name": experiment.name,
            "status": ExperimentStatus.RUNNING.value,
            "message": f"Experiment started. {experiment.treatment_percentage}% of {experiment.task_type} traffic will go to treatment."
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error starting experiment {experiment_id}: {e}")
        raise
    finally:
        await db.close()


async def stop_experiment(experiment_id: str, updated_by: Optional[str] = None) -> Dict[str, Any]:
    """Stop a running experiment"""
    db: AsyncSession = AppDatabase()
    try:
        # Get experiment
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.id == experiment_id)
        )
        experiment = result.scalar()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found"
            )
        
        if experiment.status == ExperimentStatus.STOPPED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Experiment is already stopped"
            )
        
        # Stop the experiment
        await db.execute(
            update(ABExperiment)
            .where(ABExperiment.id == experiment_id)
            .values(
                status=ExperimentStatus.STOPPED,
                stopped_at=datetime.utcnow(),
                updated_by=updated_by
            )
        )
        await db.commit()
        
        logger.info(f"Stopped experiment '{experiment.name}' (ID: {experiment_id})")
        
        return {
            "id": str(experiment.id),
            "name": experiment.name,
            "status": ExperimentStatus.STOPPED.value,
            "message": "Experiment stopped. All traffic will now use default routing."
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error stopping experiment {experiment_id}: {e}")
        raise
    finally:
        await db.close()


# ---- Delete ----

async def delete_experiment(experiment_id: str) -> bool:
    """Delete an experiment (only DRAFT or STOPPED experiments can be deleted)"""
    db: AsyncSession = AppDatabase()
    try:
        result = await db.execute(
            select(ABExperiment).where(ABExperiment.id == experiment_id)
        )
        experiment = result.scalar()
        
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found"
            )
        
        if experiment.status == ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete a running experiment. Stop it first."
            )
        
        await db.delete(experiment)
        await db.commit()
        
        logger.info(f"Deleted experiment '{experiment.name}' (ID: {experiment_id})")
        return True
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error deleting experiment {experiment_id}: {e}")
        raise
    finally:
        await db.close()


# ---- Variant Resolution (THE KEY FUNCTION) ----

async def resolve_variant(
    task_type: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    request_id: Optional[str] = None,
    redis_client=None
) -> VariantResolution:
    """
    Determine which service variant to use for a request.
    
    This is the main function called by inference services to decide routing.
    
    Args:
        task_type: The task type (asr, nmt, tts, etc.)
        user_id: User ID for sticky assignment
        tenant_id: Tenant ID for sticky assignment
        request_id: Request ID (used if no user_id/tenant_id)
        redis_client: Optional Redis client for caching
        
    Returns:
        VariantResolution with service_id, variant name, and experiment info
    """
    # Try to get from cache first
    if redis_client:
        cache_key = f"ab_exp:active:{task_type}"
        try:
            cached = await redis_client.get(cache_key)
            if cached == b"none":
                # Cached "no experiment" result
                return VariantResolution(
                    service_id="",
                    variant="default",
                    experiment_name=None,
                    experiment_id=None
                )
        except Exception as e:
            logger.warning(f"Redis cache read failed: {e}")
    
    # Get active experiment for this task type
    experiment = await get_active_experiment_for_task(task_type)
    
    if not experiment:
        # Cache the "no experiment" result
        if redis_client:
            try:
                await redis_client.setex(f"ab_exp:active:{task_type}", EXPERIMENT_CACHE_TTL, "none")
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")
        
        return VariantResolution(
            service_id="",
            variant="default",
            experiment_name=None,
            experiment_id=None
        )
    
    # Determine assignment key for sticky routing
    # Priority: user_id > tenant_id > request_id > random
    assignment_key = user_id or tenant_id or request_id or str(datetime.utcnow().timestamp())
    
    # Compute bucket (0-99) for this user/experiment combination
    bucket = _compute_bucket(str(experiment.id), assignment_key)
    
    # Determine variant based on bucket
    if bucket < experiment.treatment_percentage:
        # Treatment group
        return VariantResolution(
            service_id=experiment.treatment_service_id,
            variant="treatment",
            experiment_name=experiment.name,
            experiment_id=str(experiment.id)
        )
    else:
        # Control group
        return VariantResolution(
            service_id=experiment.control_service_id,
            variant="control",
            experiment_name=experiment.name,
            experiment_id=str(experiment.id)
        )


# ---- Helper Functions ----

def _experiment_to_dict(experiment: ABExperiment) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dict"""
    return {
        "id": str(experiment.id),
        "name": experiment.name,
        "description": experiment.description,
        "task_type": experiment.task_type,
        "control_service_id": experiment.control_service_id,
        "treatment_service_id": experiment.treatment_service_id,
        "treatment_percentage": experiment.treatment_percentage,
        "status": experiment.status.value if experiment.status else None,
        "created_by": experiment.created_by,
        "updated_by": experiment.updated_by,
        "created_at": experiment.created_at,
        "updated_at": experiment.updated_at,
        "started_at": experiment.started_at,
        "stopped_at": experiment.stopped_at,
    }

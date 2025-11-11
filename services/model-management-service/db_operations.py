from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from models.db_models import Model
from db_connection import get_app_db_session
from logger import logger


def save_model_to_db(payload: Model):
    """
    Save a new model entry to the database.
    Includes:
      - Duplicate model_id check
      - Record creation
      - Commit / rollback

    """
    from db_connection import AppDatabase

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
        
        payload_dict = jsonable_encoder(payload)

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
        logger.info(f"✅ Model {payload.modelId} successfully saved to DB.")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("❌ Error while saving model to DB.")
        raise Exception("Insert failed due to internal DB error") from e
    finally:
        # ✅ Always close session
        db.close()

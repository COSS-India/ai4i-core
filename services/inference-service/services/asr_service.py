"""ASR (Automatic Speech Recognition) TaskService."""

import logging
from typing import Any, Dict

from pydantic import BaseModel

from interfaces.task_service import BaseTaskService
from services.models.audio_models import ASRDefaultModel

logger = logging.getLogger(__name__)


class ASRTaskService(BaseTaskService):
    """
    Registry entry point for ASR inference.
    Delegates all work to ASRDefaultModel which owns the full pipeline.
    """

    def __init__(self, **dependencies: Any):
        super().__init__()
        self.model = ASRDefaultModel()
        self.logger = logger

    # -- ABC satisfaction: delegate to model ---------------------------------

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> BaseModel:
        return await self.model._deserialize_payload(payload)

    async def run_inference(self, request: BaseModel, **kwargs: Any) -> BaseModel:
        return await self.model.run_inference(request)

    # -- Override process to use the full AudioBase pipeline -----------------

    async def process(self, payload: dict, **kwargs: Any) -> Any:
        request = await self.model._deserialize_payload(payload)
        await self.model.validate_request(request)
        request.audio = await self.model.preprocess_input(request.audio)
        return await self.model.run_inference(request)

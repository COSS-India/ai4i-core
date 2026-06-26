import yaml
from pathlib import Path

from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(
    prefix="/inference-types",
    tags=["Inference Types"],
)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "inference_types.yaml"

with _CONFIG_PATH.open() as _f:
    _INFERENCE_TYPES: list = yaml.safe_load(_f)["inference_types"]


@router.get("")
async def list_inference_types():
    return success_response({"inference_types": _INFERENCE_TYPES})

"""
Model listing API endpoints (v2).
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/models",
    tags=["Model Management"],
)


@router.get("")
async def list_models_v2() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": "llama3.1:8b",
                "object": "model",
                "created": 1755000000,
                "owned_by": "library",
            },
            {
                "id": "mistral:7b",
                "object": "model",
                "created": 1754500000,
                "owned_by": "library",
            },
        ],
    }

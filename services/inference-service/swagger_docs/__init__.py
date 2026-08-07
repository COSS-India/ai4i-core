import json
from pathlib import Path
from typing import Any, Dict

_SWAGGER_PATH = Path(__file__).with_name("swagger.json")

with _SWAGGER_PATH.open(encoding="utf-8") as _f:
    _docs: Dict[str, Any] = json.load(_f)

_CHAT_EXAMPLE: Dict[str, Any] = _docs["chat_example"]
_CHAT_RESPONSE_EXAMPLE: Dict[str, Any] = _docs["chat_response_example"]
_CHAT_OPENAPI_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    int(code) if str(code).isdigit() else code: spec
    for code, spec in _docs["chat_openapi_responses"].items()
}
_CHAT_OPENAPI_RESPONSES[200]["content"]["application/json"]["example"] = (
    _CHAT_RESPONSE_EXAMPLE
)

__all__ = [
    "_CHAT_EXAMPLE",
    "_CHAT_OPENAPI_RESPONSES",
    "_CHAT_RESPONSE_EXAMPLE",
]

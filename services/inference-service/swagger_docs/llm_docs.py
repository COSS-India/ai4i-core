from typing import Any, Dict, Optional, Tuple

_CHAT_EXAMPLE = {
    "model": "llm-service-1",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": False,
}


# OpenAPI response example for chat / try-it (runtime body is upstream-passthrough).
_CHAT_RESPONSE_EXAMPLE = {
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "llm-service-1",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello! How can I help you?"},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 9,
        "completion_tokens": 12,
        "total_tokens": 21,
    },
}

_CHAT_OPENAPI_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    200: {
        "description": "Successful Response",
        "content": {
            "application/json": {"example": _CHAT_RESPONSE_EXAMPLE},
        },
    },
}

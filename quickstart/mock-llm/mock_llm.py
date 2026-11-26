"""A tiny OpenAI-compatible chat model for the quick start.

It answers every chat request by echoing the last user message, so a new
developer can register a model and run inference with no GPU, no download and
no provider key. Standard library only. Not a real model, never deploy it.

Endpoints:
    GET  /health
    GET  /v1/models
    POST /v1/chat/completions   (JSON, or server-sent events when "stream": true)
"""
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_NAME = os.getenv("MOCK_MODEL_NAME", "quickstart/echo-llm")
PORT = int(os.getenv("PORT", "8000"))


def _tokens(text: str) -> int:
    """Rough token count, one per whitespace-separated word."""
    return max(1, len(text.split()))


def _reply_for(messages: list) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return f"Echo from the quick start model: {content}"
    return "Echo from the quick start model: (no user message)"


def _usage(messages: list, reply: str) -> dict:
    prompt = sum(_tokens(str(m.get("content", ""))) for m in messages or [])
    completion = _tokens(reply)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "quickstart-mock-llm/1.0"

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path.rstrip("/") == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "quickstart"}],
            })
        else:
            self._send_json(404, {"error": {"message": f"Unknown path {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": f"Unknown path {self.path}"}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": {"message": "Request body must be JSON"}})
            return

        messages = request.get("messages") or []
        model = request.get("model") or MODEL_NAME
        reply = _reply_for(messages)
        usage = _usage(messages, reply)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        if request.get("stream"):
            self._stream(completion_id, created, model, reply, usage, request)
            return

        self._send_json(200, {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }],
            "usage": usage,
        })

    def _stream(self, completion_id, created, model, reply, usage, request) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def chunk(delta: dict, finish_reason=None, chunk_usage=None) -> None:
            body = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [] if chunk_usage else [
                    {"index": 0, "delta": delta, "finish_reason": finish_reason}
                ],
            }
            if chunk_usage:
                body["usage"] = chunk_usage
            self.wfile.write(f"data: {json.dumps(body)}\n\n".encode())
            self.wfile.flush()

        chunk({"role": "assistant", "content": ""})
        for word in reply.split(" "):
            chunk({"content": word + " "})
        chunk({}, finish_reason="stop")
        if (request.get("stream_options") or {}).get("include_usage"):
            chunk({}, chunk_usage=usage)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, fmt: str, *args) -> None:
        print(f"mock-llm {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"mock-llm serving {MODEL_NAME} on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

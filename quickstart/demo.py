#!/usr/bin/env python3
"""Quick start walkthrough: register the sample model and run one inference.

Does, through the gateway, what an Adopter Admin and an Institution Admin do in
the portal:

  1. Sign in as the seeded admin.
  2. Create and activate a tier with an LLM quota.
  3. Register the sample model (the offline echo model in the mock-llm container).
  4. Create a service for it on that tier, and publish it.
  5. Give the admin's institution the tier and a budget.
  6. Create an application and an API key under it.
  7. Send a chat request with the API key.

Safe to run again: it reuses what already exists and only creates a new API
key each time (keys are shown once). Standard library only.

    python3 quickstart/demo.py [--gateway http://localhost:8080]
"""
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

ADMIN_EMAIL = "admin@ai4inclusion.org"
ADMIN_PASSWORD = "Admin@12345"

TIER_NAME = "Quickstart"
MODEL_NAME = "quickstart/echo-llm"
MODEL_VERSION = "v1"
SERVICE_ID = "quickstart-echo-llm"
MODEL_ENDPOINT = "http://mock-llm:8000"  # container name: the platform calls it inside Docker
APPLICATION_NAME = "Quickstart App"
TENANT_BUDGET = 100000
KEY_BUDGET = 100

MODEL_PAYLOAD = {
    "name": MODEL_NAME,
    "version": MODEL_VERSION,
    "description": "Sample chat model for the quick start. It echoes the prompt back and runs offline.",
    "task": {"type": "llm"},
    "license": "mit",
    "domain": ["general"],
    "submitter": {"name": "Quick Start"},
    "trainingDataset": {"description": "None. The sample model echoes the prompt and has no training data."},
    "callbackUrl": MODEL_ENDPOINT,
    "isSyncApi": True,
    # For an LLM, model_name is the name the model server expects in "model".
    # inputs/outputs are required placeholders; LLM requests do not use them.
    "adapterConfig": {
        "version": "1.0",
        "model_name": MODEL_NAME,
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target"}],
    },
    "schema": {
        "taskType": "llm",
        "model_name": MODEL_NAME,
        "request": {"messages": [{"role": "user", "content": "Say hello in one line"}], "max_tokens": 64},
        "response": {
            "id": "chatcmpl-quickstart",
            "object": "chat.completion",
            "created": 1789465507,
            "model": MODEL_NAME,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Echo from the quick start model: Say hello in one line"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 11, "total_tokens": 16},
        },
    },
}


class ApiError(RuntimeError):
    pass


class Gateway:
    """Minimal JSON client for the quick start gateway."""

    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/") + "/api/v1"
        self.token = None

    def call(self, method: str, path: str, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        bearer = token or self.token
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise ApiError(f"{method} {path} returned {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise ApiError(
                f"Cannot reach {self.base}: {exc.reason}. Is the stack up? "
                "Run: docker compose -f quickstart/docker-compose.yml up -d"
            ) from None
        return json.loads(raw) if raw else None


def step(number: int, text: str) -> None:
    print(f"\n{number}. {text}")


def done(text: str) -> None:
    print(f"   {text}")


def sign_in(gw: Gateway) -> str:
    step(1, f"Sign in as {ADMIN_EMAIL}")
    gw.token = gw.call("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})["access_token"]
    tenant_id = str(gw.call("GET", "/auth/me")["data"]["tenant_id"])
    done(f"signed in, institution (tenant) id {tenant_id}")
    return tenant_id


def ensure_tier(gw: Gateway) -> str:
    step(2, f"Tier '{TIER_NAME}' with an LLM quota")
    tier = next((t for t in gw.call("GET", "/pay-per-use/tiers")["data"] if t["name"] == TIER_NAME), None)
    if tier is None:
        tier = gw.call("POST", "/pay-per-use/tier", {
            "name": TIER_NAME,
            "description": "Tier for the quick start sample model",
            "rateLimit": 60,
            "quotas": [{"modelTaskType": "llm", "limit": 1_000_000}],
        })
        done(f"created {tier['id']}")
    else:
        done(f"already exists: {tier['id']}")
    if tier["status"] != "ACTIVE":
        gw.call("PATCH", f"/pay-per-use/tier/{tier['id']}/status", {"status": "ACTIVE"})
        done("activated")
    return tier["id"]


def ensure_model(gw: Gateway) -> str:
    step(3, f"Model '{MODEL_NAME}' {MODEL_VERSION}, endpoint {MODEL_ENDPOINT}")
    models = gw.call("GET", "/models/list")["data"]
    model = next((m for m in models if m["name"] == MODEL_NAME and m["version"] == MODEL_VERSION), None)
    if model:
        done(f"already registered: {model['modelId']}")
        return model["modelId"]
    model_id = gw.call("POST", "/models/list", MODEL_PAYLOAD)["data"]["modelId"]
    done(f"registered: {model_id}")
    return model_id


def ensure_service(gw: Gateway, model_id: str, tier_id: str) -> None:
    step(4, f"Service '{SERVICE_ID}' on tier '{TIER_NAME}', published")
    services = gw.call("GET", "/services")["data"]["services"]
    service = next((s for s in services if s["serviceId"] == SERVICE_ID), None)
    if service is None:
        # Creating a service makes the platform call the model once to check it.
        gw.call("POST", "/services", {
            "serviceId": SERVICE_ID,
            "name": SERVICE_ID,
            "description": "Quick start sample chat service backed by the offline echo model.",
            "modelId": model_id,
            "modelVersion": MODEL_VERSION,
            "task": {"type": "llm"},
            "endpoint": MODEL_ENDPOINT,
            "inferenceServerType": "custom",
            "sslVerify": False,
            # LLM pricing, per unitSize tokens.
            "costPerUnit": 0.01,
            "cachedInputCostPerUnit": 0.005,
            "outputCostPerUnit": 0.02,
            "unitSize": 1000,
            "tierIds": [tier_id],
        })
        done("created, endpoint check passed")
    else:
        done("already exists")
    if not (service or {}).get("isPublished"):
        gw.call("PATCH", "/services", {"serviceId": SERVICE_ID, "isPublished": True})
        done("published")


def ensure_institution(gw: Gateway, tenant_id: str, tier_id: str) -> None:
    step(5, "Institution tier and budget")
    tenant = gw.call("GET", f"/auth/tenants/{tenant_id}")["data"]
    if tenant.get("tier_id") != tier_id:
        gw.call("PATCH", f"/auth/tenants/{tenant_id}/tier", {"tier_id": tier_id})
        done(f"assigned tier '{TIER_NAME}'")
    else:
        done(f"tier '{TIER_NAME}' already assigned")
    if not tenant.get("allocated_budget"):
        today = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        gw.call("PATCH", f"/auth/tenants/{tenant_id}/budget", {
            "action": "top-up",
            "amount": TENANT_BUDGET,
            "budget_effective_from": today.isoformat().replace("+00:00", "Z"),
            "budget_effective_to": (today + dt.timedelta(days=365)).isoformat().replace("+00:00", "Z"),
        })
        done(f"budget {TENANT_BUDGET} for one year")
    else:
        done(f"budget already set: {tenant['allocated_budget']}")


def ensure_application(gw: Gateway, tenant_id: str) -> int:
    step(6, f"Application '{APPLICATION_NAME}' and an API key")
    apps = gw.call("GET", f"/auth/tenants/{tenant_id}/applications")["data"]["items"]
    app = next((a for a in apps if a["name"] == APPLICATION_NAME), None)
    if app is None:
        app = gw.call("POST", f"/auth/tenants/{tenant_id}/applications", {
            "name": APPLICATION_NAME,
            "description": "Application for the quick start walkthrough",
            "allocated_percentage": 50,
        })["data"]
        done(f"application created: id {app['id']}")
    else:
        done(f"application already exists: id {app['id']}")
    return app["id"]


def create_api_key(gw: Gateway, application_id: int) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    key = gw.call("POST", "/auth/api-keys", {
        "application_id": application_id,
        "key_name": f"quickstart-{stamp}",
        "permissions": ["llm.inference"],
        "budget": KEY_BUDGET,
    })["data"]["api_key"]
    done("API key created (shown once, printed at the end)")
    return key


def chat(gw: Gateway, api_key: str) -> None:
    step(7, "Chat request with the API key")
    reply = gw.call("POST", "/chat/completions", {
        "model": SERVICE_ID,
        "messages": [{"role": "user", "content": "Say hello in five words."}],
    }, token=api_key)
    done(f"reply: {reply['choices'][0]['message']['content']}")
    done(f"usage: {reply.get('usage')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", default="http://localhost:8080", help="gateway URL (default: %(default)s)")
    args = parser.parse_args()
    gw = Gateway(args.gateway)
    try:
        tenant_id = sign_in(gw)
        tier_id = ensure_tier(gw)
        model_id = ensure_model(gw)
        ensure_service(gw, model_id, tier_id)
        ensure_institution(gw, tenant_id, tier_id)
        application_id = ensure_application(gw, tenant_id)
        api_key = create_api_key(gw, application_id)
        chat(gw, api_key)
    except ApiError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print(f"""
Done. Try it yourself:

  curl -s {args.gateway}/api/v1/chat/completions \\
    -H 'Authorization: Bearer {api_key}' \\
    -H 'Content-Type: application/json' \\
    -d '{{"model": "{SERVICE_ID}", "messages": [{{"role": "user", "content": "Hello"}}]}}'

The request shows on the Usage Dashboard ({args.gateway}) within about a minute.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())

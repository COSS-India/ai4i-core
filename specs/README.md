# Public API Specs (OpenAPI)

Public API specs and the docs registry are maintained in the **Docs Manager** service:

- **`services/docs-manager/specs/`**
  - **`service-docs-registry.yaml`** – Registry of services and their spec file names. `api_gateway_url` is used for "Try it out" in Swagger.
  - **`<service-name>.yaml`** – One OpenAPI 3.0 YAML per service (e.g. `asr-service.yaml`, `auth-service.yaml`). See the registry for the full list.

The **Docs Manager** merges these into a single OpenAPI spec and serves one Swagger UI:

- **Swagger UI**: http://localhost:8103/docs  
- **Merged OpenAPI JSON**: http://localhost:8103/openapi.json  

Run the aggregator:

- Docker: `docker compose -f docker-compose-local.yml up docs-manager`
- Local: from repo root, `uvicorn main:app --port 8103 --app-dir services/docs-manager`

To add or update a service: edit or add `services/docs-manager/specs/<service-name>.yaml` and ensure it is listed in `service-docs-registry.yaml` in the same folder.

# Docs Manager – Specs

This folder contains the registry and all per-service OpenAPI YAMLs used to build the unified Swagger UI.

## Layout

- **`service-docs-registry.yaml`** – Lists each service and its `spec_file` (filename in this folder). Do not remove.
- **`<service-name>.yaml`** – One OpenAPI 3.0 spec per public service (asr-service, tts-service, auth-service, etc.).

## Adding or updating a service

1. Add or edit `<service-name>.yaml` with the public API paths for that service (as exposed via the API Gateway).
2. Add or update the entry in `service-docs-registry.yaml` with `spec_file: "<service-name>.yaml"` and a `description` for the Swagger UI section title.

Specs are merged at runtime; no rebuild required when editing YAMLs (with the Docker volume mount or local run).

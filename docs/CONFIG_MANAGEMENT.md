# Config Management

## Purpose

A single, generic backend facility for storing admin-configurable lists/dropdowns
used across the platform, without needing a new table or migration every time a
new configurable list is needed.

Instead of hardcoding dropdown options or column catalogs, define a `type` and
let admins maintain the values through `/api/v1/config`.

## How it works

One table, `configs`, backs every config type:

| Column       | Type      | Notes                                          |
|--------------|-----------|-------------------------------------------------|
| `id`         | int       | PK                                               |
| `type`       | string    | Unique identifier for the config (e.g. `domain`) |
| `data`       | JSONB     | Free-form payload — shape is owned by the `type` |
| `is_default` | bool      | Seed configs; cannot be deleted via API          |
| `created_by` / `updated_by` / timestamps | | Audit trail |

The API and service layer (`app/routes/config.py`,
`app/services/config_management/config_service.py`) never interpret `data` —
they just store/return it. Each consumer (frontend component or backend
feature) defines and owns the shape for its own `type`.

## API

| Method | Path                  | Access      | Purpose                           |
|--------|-----------------------|-------------|------------------------------------|
| GET    | `/api/v1/config`      | Any authenticated role | List configs, optional `?type=` filter, optional `?sort_order=asc\|desc` |
| GET    | `/api/v1/config/{id}` | Admin       | Fetch one config by id            |
| POST   | `/api/v1/config`      | Admin       | Create a new config (`type` must be unique) |
| PUT    | `/api/v1/config/{id}` | Admin       | Partial update (`type` and/or `data`) |
| DELETE | `/api/v1/config/{id}` | Admin       | Delete (blocked if `is_default=true`) |

Example — create a new config:
```bash
curl -X POST /api/v1/config \
  -H "Content-Type: application/json" \
  -d '{"type": "suspend-reasons", "data": [{"key":"abuse","label":"Abuse"}]}'
```

Example — read it back for a dropdown:
```bash
GET /api/v1/config?type=suspend-reasons&sort_order=asc
```

## Config types currently in use

| `type`           | Consumer                                                                 | `data` shape |
|-------------------|---------------------------------------------------------------------|--------------|
| `domain`           | PII policy domain picker (`drawers.tsx`)                            | `[{key, label, required?}]` |
| `model-column`     | Model List column catalog (`modelListColumns.ts`)                   | `[{key, label, required?, defaultVisible?}]` |
| `service-column`   | Service List column catalog (`serviceListColumns.ts`)               | `[{columns: [{id, label, mandatory?, sortable?, ...}]}]` |
| `suspend-reasons`   | Institution suspend dialog (`InstitutionConfirmDialogs.tsx`)        | `[{key, label, required?}]` |
| `deactivate-reasons`| Institution deactivate dialog (`InstitutionConfirmDialogs.tsx`)     | `[{key, label, required?}]` |

## Adding a new configurable list

1. Decide on a unique `type` string and the JSON shape of `data`.
2. Seed it (migration or admin API call) with `is_default=true` if it must
   always exist.
3. In the consuming frontend/backend code, fetch via
   `GET /api/v1/config?type=<your-type>` and parse `data` according to your
   chosen shape — no backend route/model changes required.
4. Document the new `type` and its `data` shape in the table above.

## Limitations

- No admin UI yet — configs must be created/edited via direct API calls.
- `data` has no server-side JSON-schema validation per `type`; malformed data
  will surface as a frontend parsing issue, not an API error.

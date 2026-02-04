# Model Management Service Documentation

Welcome to the Model Management Service documentation.

## Documentation Index

### [Model Versioning Guide](./MODEL_VERSIONING.md)
Comprehensive guide to model versioning features, including:
- Multiple versions per model
- Version status management (ACTIVE/DEPRECATED)
- Active version limits
- Service association with specific versions
- API changes and examples
- Migration guide
- Best practices

## Quick Links

- **Model Versioning**: See [MODEL_VERSIONING.md](./MODEL_VERSIONING.md) for complete details
- **API Documentation**: Available at `/docs` endpoint when service is running
- **Environment Configuration**: See `env.template` in service root

## Getting Started

1. **Configure Environment**: Copy `env.template` to `.env` and set required variables
2. **Run Migration**: Execute the migration scripts in `infrastructure/postgres/` directory
3. **Start Service**: Use Docker Compose or run directly with `python main.py`

## Key Features

- ✅ Model versioning with status management
- ✅ Configurable active version limits
- ✅ Service-to-version association
- ✅ Deterministic hash-based ID generation
- ✅ RESTful API endpoints
- ✅ Redis caching support
- ✅ Authentication and authorization

---

## Database Schema

### Overview

The Model Management Service uses PostgreSQL with two primary tables:
- `models` - Stores model metadata and versioning information
- `services` - Stores service configurations linked to specific model versions

### ID Generation

The system uses **deterministic SHA256 hashing** to generate unique identifiers for models and services. This ensures IDs are reproducible and eliminates user-provided ID conflicts.

#### Model ID Generation

```
model_id = SHA256(lowercase(model_name) + ":" + lowercase(version))[:32]
```

| Input | Processing |
|-------|------------|
| `model_name` | Trimmed and converted to lowercase |
| `version` | Trimmed and converted to lowercase |
| **Hash Input** | `"{model_name}:{version}"` |
| **Output** | First 32 characters of SHA256 hex digest |

**Example:**
```
Input:  name="ASR Model", version="1.0.0"
Hash:   SHA256("asr model:1.0.0")
Result: "a7f3b2c1d4e5f6789012345678901234" (32 chars)
```

#### Service ID Generation

```
service_id = SHA256(lowercase(model_name) + ":" + lowercase(model_version) + ":" + lowercase(service_name))[:32]
```

| Input | Processing |
|-------|------------|
| `model_name` | Trimmed and converted to lowercase |
| `model_version` | Trimmed and converted to lowercase |
| `service_name` | Trimmed and converted to lowercase |
| **Hash Input** | `"{model_name}:{model_version}:{service_name}"` |
| **Output** | First 32 characters of SHA256 hex digest |

**Example:**
```
Input:  model_name="ASR Model", model_version="1.0.0", service_name="ASR Service"
Hash:   SHA256("asr model:1.0.0:asr service")
Result: "b8e4c5d6f7a89012345678901234abcd" (32 chars)
```

### Models Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Internal UUID, auto-generated |
| `model_id` | VARCHAR(255) | NOT NULL | Hash-based ID from (name, version) |
| `name` | VARCHAR(255) | NOT NULL, UNIQUE(name, version) | Human-readable model name |
| `version` | VARCHAR(100) | NOT NULL, UNIQUE(name, version) | Model version string |
| `version_status` | ENUM | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE or DEPRECATED |
| `version_status_updated_at` | TIMESTAMP | DEFAULT NOW() | Auto-updated when status changes |
| `description` | TEXT | | Model description |
| `ref_url` | VARCHAR(500) | | Reference documentation URL |
| `task` | JSONB | NOT NULL | Task type configuration |
| `languages` | JSONB | NOT NULL, DEFAULT [] | Supported languages |
| `license` | VARCHAR(255) | | License type |
| `domain` | JSONB | NOT NULL, DEFAULT [] | Application domains |
| `inference_endpoint` | JSONB | NOT NULL | Endpoint configuration |
| `benchmarks` | JSONB | | Performance benchmarks |
| `submitter` | JSONB | NOT NULL | Submitter information |
| `submitted_on` | BIGINT | NOT NULL | Unix timestamp of creation |
| `updated_on` | BIGINT | | Unix timestamp of last update |
| `created_by` | VARCHAR(255) | | User ID who created |
| `updated_by` | VARCHAR(255) | | User ID who last updated |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Record update timestamp |

### Services Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Internal UUID, auto-generated |
| `service_id` | VARCHAR(255) | UNIQUE, NOT NULL | Hash-based ID from (model_name, model_version, service_name) |
| `name` | VARCHAR(255) | NOT NULL | Human-readable service name |
| `model_id` | VARCHAR(255) | NOT NULL, FK | Reference to model's model_id |
| `model_version` | VARCHAR(100) | NOT NULL, FK | Reference to model's version |
| `endpoint` | VARCHAR(500) | NOT NULL | Service endpoint URL |
| `api_key` | VARCHAR(255) | | API key for authentication |
| `service_description` | TEXT | | Service description |
| `hardware_description` | TEXT | | Hardware specifications |
| `health_status` | JSONB | | Health check status |
| `benchmarks` | JSONB | | Performance benchmarks |
| `is_published` | BOOLEAN | NOT NULL, DEFAULT FALSE | Publication status |
| `published_on` | BIGINT | NOT NULL | Unix timestamp of creation |
| `published_at` | BIGINT | | Unix timestamp when published |
| `unpublished_at` | BIGINT | | Unix timestamp when unpublished |
| `created_by` | VARCHAR(255) | | User ID who created |
| `updated_by` | VARCHAR(255) | | User ID who last updated |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Record update timestamp |

### Constraints & Indexes

**Models Table:**
- `uq_name_version` - UNIQUE(name, version)
- `idx_models_model_id_version` - INDEX(model_id, version)
- `idx_models_version_status` - INDEX(version_status)
- `idx_models_name` - INDEX(name)
- `idx_models_created_by` - INDEX(created_by)

**Services Table:**
- `uq_model_id_version_service_name` - UNIQUE(model_id, model_version, name)
- `services_model_id_fkey` - FK(model_id, model_version) REFERENCES models(model_id, version)
- `idx_services_model_id_version` - INDEX(model_id, model_version)
- `idx_services_name` - INDEX(name)
- `idx_services_is_published` - INDEX(is_published)
- `idx_services_created_by` - INDEX(created_by)

### Relationships

```
┌─────────────────────┐         ┌─────────────────────┐
│       models        │         │      services       │
├─────────────────────┤         ├─────────────────────┤
│ id (PK)             │         │ id (PK)             │
│ model_id ───────────┼────┬────┼ model_id (FK)       │
│ version ────────────┼────┘    │ model_version (FK)  │
│ name                │    1:N  │ service_id (UNIQUE) │
│ ...                 │         │ name                │
└─────────────────────┘         │ ...                 │
                                └─────────────────────┘
```

- One model (model_id + version) can have multiple services
- Each service must reference an existing model version

---

## Migration Scripts

| Script | Purpose |
|--------|---------|
| `10-model-versioning-migration.sql` | Add versioning support to models |
| `11-model-id-hash-migration.sql` | Convert model_id to hash-based |
| `12-service-id-hash-migration.sql` | Convert service_id to hash-based |
| `13-model-management-audit-logs-migration.sql` | Add created_by/updated_by audit columns |

**Note:** Run Python migration scripts (`migrate_model_id_to_hash.py`, `migrate_service_id_to_hash.py`) before SQL migrations when upgrading existing data.

---

## Support

For issues or questions, refer to:
- Service logs
- API documentation at `/docs`
- Database schema in `models/db_models.py`

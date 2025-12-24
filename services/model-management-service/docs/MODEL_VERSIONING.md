# Model Versioning Documentation

## Overview

The Model Management Service now supports multi-version model management, allowing multiple versions of the same model to coexist. This enables:

- **Version History**: Track different iterations of models over time
- **Gradual Rollouts**: Test new versions while keeping old ones available
- **Rollback Capability**: Switch services back to previous versions if needed
- **Version Lifecycle Management**: Mark versions as active or deprecated
- **Service-Version Binding**: Services are tied to specific model versions

## Table of Contents

1. [Key Concepts](#key-concepts)
2. [Database Schema](#database-schema)
3. [API Endpoints](#api-endpoints)
4. [Configuration](#configuration)
5. [Usage Examples](#usage-examples)
6. [Migration Guide](#migration-guide)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Key Concepts

### Model Versioning

- **Model ID**: The base identifier for a model (e.g., "asr-hindi-v1")
- **Version**: Semantic version string (e.g., "1.0.0", "1.1.0", "2.0.0")
- **Composite Key**: Uniqueness is enforced on `(model_id, version)` combination
- **Version Status**: Either "active" or "deprecated"
- **Immutability**: Published versions can be marked as immutable to prevent modifications

### Service-Version Relationship

- Each service is bound to a specific model version
- Services can be switched to different versions of the same model
- The system tracks when a service's version was last updated
- Deprecated versions can optionally be used by services (configurable)

## Database Schema

### Models Table Changes

```sql
-- New columns added
version_status VARCHAR(50) NOT NULL DEFAULT 'active'
release_notes TEXT
is_immutable BOOLEAN NOT NULL DEFAULT FALSE

-- Constraints
UNIQUE (model_id, version)  -- Composite unique constraint
INDEX (model_id, version)
INDEX (model_id, version_status)
```

### Services Table Changes

```sql
-- New columns added
model_version VARCHAR(100) NOT NULL
version_updated_at BIGINT

-- Indexes
INDEX (model_id, model_version)
```

### Migration

Run the migration script before deploying:

```bash
psql -U dhruva_user -d model_management_db -f migrations/add_model_versioning.sql
```

## API Endpoints

### Model Version Management

#### List All Versions of a Model

```http
GET /models/{model_id}/versions
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "version": "1.0.0",
    "versionStatus": "active",
    "releaseNotes": "Initial release",
    "isPublished": true,
    "isImmutable": true,
    "publishedAt": "2024-01-15T10:00:00Z",
    "createdAt": "2024-01-15T09:00:00Z"
  },
  {
    "version": "1.1.0",
    "versionStatus": "active",
    "releaseNotes": "Performance improvements",
    "isPublished": true,
    "isImmutable": false,
    "publishedAt": "2024-02-01T10:00:00Z",
    "createdAt": "2024-02-01T09:00:00Z"
  }
]
```

#### Create New Version

```http
POST /models/{model_id}/versions
Authorization: Bearer <token>
Content-Type: application/json

{
  "version": "1.2.0",
  "releaseNotes": "Bug fixes and optimizations",
  "versionStatus": "active"
}
```

**Requirements:**
- User must have Moderator role
- Base model must exist
- Version must follow semantic versioning (e.g., "1.0.0")
- Version must not already exist
- Active version limit must not be exceeded (default: 5)

#### Get Model by Version

```http
GET /models/{model_id}?version=1.2.0
Authorization: Bearer <token>
```

**Query Parameters:**
- `version` (optional): Specific version to retrieve. Defaults to latest active version.

**Response:**
```json
{
  "modelId": "asr-hindi-v1",
  "version": "1.2.0",
  "uuid": "...",
  "name": "Hindi ASR Model",
  "versionStatus": "active",
  "releaseNotes": "Bug fixes and optimizations",
  "isImmutable": false,
  "allVersions": ["1.2.0", "1.1.0", "1.0.0"],
  ...
}
```

#### Deprecate Version

```http
PATCH /models/{model_id}/versions/{version}/deprecate
Authorization: Bearer <token>
```

**Requirements:**
- User must have Moderator role

#### Publish/Unpublish Version

```http
POST /models/publish?model_id={model_id}&version={version}
POST /models/unpublish?model_id={model_id}&version={version}
Authorization: Bearer <token>
```

**Note:** Publishing a version sets `is_immutable=true` if `ENABLE_VERSION_IMMUTABILITY=true`

### Service Version Management

#### Create Service with Version

```http
POST /services/admin/create/service
Content-Type: application/json

{
  "serviceId": "asr-service-1",
  "name": "Hindi ASR Service",
  "modelId": "asr-hindi-v1",
  "modelVersion": "1.2.0",  // Required: specifies which version to use
  "endpoint": "http://asr-service:8080",
  ...
}
```

#### Switch Service Version

```http
PATCH /services/admin/update/service/version?service_id={service_id}&new_version={new_version}
```

**Requirements:**
- New version must exist
- New version must not be deprecated (unless `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH=true`)

#### Get Available Versions for Service

```http
GET /services/{service_id}/available-versions
Authorization: Bearer <token>
```

**Response:**
```json
{
  "availableVersions": ["1.2.0", "1.1.0", "1.0.0"]
}
```

#### List Services by Model Version

```http
GET /services/admin/model/{model_id}/version/{version}/services
```

**Response:**
```json
[
  {
    "serviceId": "asr-service-1",
    "name": "Hindi ASR Service",
    "endpoint": "http://asr-service:8080"
  }
]
```

#### Find Services Using Deprecated Versions

```http
GET /services/admin/model/{model_id}/deprecated-version-services
```

**Response:**
```json
[
  {
    "serviceId": "asr-service-2",
    "name": "Legacy ASR Service",
    "endpoint": "http://asr-service-2:8080",
    "modelVersion": "1.0.0",
    "versionStatus": "deprecated"
  }
]
```

### Filtering and Querying

#### List Models with Version Status Filter

```http
GET /models?version_status=active
GET /models?version_status=deprecated
Authorization: Bearer <token>
```

#### List Services with Version Filter

```http
GET /services/details/list_services?model_version=1.2.0
```

## Configuration

### Environment Variables

Add these to your `.env` file or `env.template`:

```bash
# Version management configuration
MAX_ACTIVE_VERSIONS_PER_MODEL=5
DEFAULT_VERSION_STATUS=active
ENABLE_VERSION_IMMUTABILITY=true
ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH=false
WARN_ON_DEPRECATED_VERSION_USAGE=true
```

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ACTIVE_VERSIONS_PER_MODEL` | 5 | Maximum number of active versions allowed per model |
| `DEFAULT_VERSION_STATUS` | "active" | Default status for new versions |
| `ENABLE_VERSION_IMMUTABILITY` | true | Set versions as immutable when published |
| `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH` | false | Allow services to switch to deprecated versions |
| `WARN_ON_DEPRECATED_VERSION_USAGE` | true | Log warnings when services use deprecated versions |

## Usage Examples

### Example 1: Creating and Managing Model Versions

```python
# 1. Create initial model version
POST /models
{
  "modelId": "asr-hindi-v1",
  "version": "1.0.0",
  "name": "Hindi ASR Model",
  "releaseNotes": "Initial release",
  ...
}

# 2. Create new version with improvements
POST /models/asr-hindi-v1/versions
{
  "version": "1.1.0",
  "releaseNotes": "Improved accuracy on noisy audio",
  "versionStatus": "active"
}

# 3. Publish the new version
POST /models/publish?model_id=asr-hindi-v1&version=1.1.0

# 4. Deprecate old version after migration
PATCH /models/asr-hindi-v1/versions/1.0.0/deprecate
```

### Example 2: Service Version Management

```python
# 1. Create service with specific version
POST /services/admin/create/service
{
  "serviceId": "asr-service-prod",
  "modelId": "asr-hindi-v1",
  "modelVersion": "1.1.0",  # Use latest version
  ...
}

# 2. Switch service to new version
PATCH /services/admin/update/service/version?service_id=asr-service-prod&new_version=1.2.0

# 3. Check which services use deprecated versions
GET /services/admin/model/asr-hindi-v1/deprecated-version-services
```

### Example 3: Version Lifecycle

```python
# 1. Create version 1.0.0 (active)
POST /models/asr-hindi-v1/versions
{"version": "1.0.0", "versionStatus": "active"}

# 2. Create version 1.1.0 (active)
POST /models/asr-hindi-v1/versions
{"version": "1.1.0", "versionStatus": "active"}

# 3. Create version 1.2.0 (active) - may auto-deprecate oldest if limit exceeded
POST /models/asr-hindi-v1/versions
{"version": "1.2.0", "versionStatus": "active"}

# 4. Manually deprecate old version
PATCH /models/asr-hindi-v1/versions/1.0.0/deprecate

# 5. List all versions
GET /models/asr-hindi-v1/versions
# Returns: [1.2.0 (active), 1.1.0 (active), 1.0.0 (deprecated)]
```

## Migration Guide

### Step 1: Backup Database

```bash
pg_dump -U dhruva_user -d model_management_db > backup_before_versioning.sql
```

### Step 2: Run Migration Script

```bash
psql -U dhruva_user -d model_management_db -f services/model-management-service/migrations/add_model_versioning.sql
```

### Step 3: Verify Migration

```sql
-- Check new columns exist
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'models' 
AND column_name IN ('version_status', 'release_notes', 'is_immutable');

-- Check services have model_version
SELECT service_id, model_id, model_version 
FROM services 
LIMIT 5;

-- Check constraints
SELECT conname, contype 
FROM pg_constraint 
WHERE conrelid = 'models'::regclass 
AND conname = 'uq_model_id_version';
```

### Step 4: Update Application Code

1. Deploy updated service code
2. Restart the service
3. Verify endpoints are working

### Step 5: Update Existing Data (if needed)

If you have existing models without versions, they will have default version "1.0.0" and status "active". You may want to:

```sql
-- Update existing models to have explicit versions
UPDATE models 
SET version = '1.0.0' 
WHERE version IS NULL OR version = '';

-- Ensure all have active status
UPDATE models 
SET version_status = 'active' 
WHERE version_status IS NULL;
```

## Best Practices

### Version Naming

- Use semantic versioning: `MAJOR.MINOR.PATCH` (e.g., "1.0.0", "1.1.0", "2.0.0")
- Major version: Breaking changes
- Minor version: New features, backward compatible
- Patch version: Bug fixes

### Version Lifecycle

1. **Create** → Version created with status "active"
2. **Test** → Use in non-production services first
3. **Publish** → Mark as published (becomes immutable if configured)
4. **Migrate** → Switch production services to new version
5. **Deprecate** → Mark old versions as deprecated after migration
6. **Monitor** → Check for services still using deprecated versions

### Service Version Management

- Always test new versions in staging first
- Use gradual rollouts: switch a few services, monitor, then expand
- Keep at least one previous version active for quick rollback
- Document version changes in `releaseNotes`
- Monitor services using deprecated versions

### Active Version Limits

- Default limit is 5 active versions per model
- System will auto-deprecate oldest versions if limit exceeded
- Adjust `MAX_ACTIVE_VERSIONS_PER_MODEL` based on your needs
- Consider deprecating old versions manually before creating new ones

### Immutability

- Published versions become immutable by default
- This prevents accidental modifications to production models
- To modify, create a new version instead
- Set `ENABLE_VERSION_IMMUTABILITY=false` to allow modifications (not recommended)

## Troubleshooting

### Issue: "Version already exists"

**Cause:** Trying to create a version that already exists.

**Solution:** Use a different version number or update the existing version (if not immutable).

### Issue: "Active version limit exceeded"

**Cause:** Too many active versions for a model.

**Solution:**
1. Deprecate old versions manually
2. Or increase `MAX_ACTIVE_VERSIONS_PER_MODEL`
3. System will auto-deprecate oldest if limit exceeded

### Issue: "Version is immutable and cannot be modified"

**Cause:** Trying to update a published version.

**Solution:** Create a new version instead of modifying the existing one.

### Issue: "Service cannot switch to deprecated version"

**Cause:** `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH=false` and trying to use deprecated version.

**Solution:**
1. Re-activate the version (change status to "active")
2. Or set `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH=true` (not recommended)

### Issue: "Model version not found"

**Cause:** Service references a version that doesn't exist.

**Solution:**
1. Check available versions: `GET /models/{model_id}/versions`
2. Update service to use an existing version
3. Or create the missing version

### Issue: Migration fails on existing data

**Cause:** Existing services may not have valid model versions.

**Solution:**
```sql
-- Check for services with invalid model versions
SELECT s.service_id, s.model_id, s.model_version, m.version
FROM services s
LEFT JOIN models m ON s.model_id = m.model_id AND s.model_version = m.version
WHERE m.version IS NULL;

-- Fix by updating to existing version
UPDATE services s
SET model_version = (
    SELECT version FROM models 
    WHERE model_id = s.model_id 
    ORDER BY version DESC 
    LIMIT 1
)
WHERE model_version NOT IN (
    SELECT version FROM models WHERE model_id = services.model_id
);
```

## API Reference Summary

### Model Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/models` | List all models (filter by `version_status`) | Yes |
| GET | `/models/{model_id}` | Get model (optionally by `version`) | Yes |
| POST | `/models` | Create new model (first version) | Yes |
| PATCH | `/models` | Update model (requires `version`) | Yes |
| POST | `/models/{model_id}/versions` | Create new version | Moderator |
| GET | `/models/{model_id}/versions` | List all versions | Moderator |
| PATCH | `/models/{model_id}/versions/{version}/deprecate` | Deprecate version | Moderator |
| POST | `/models/publish` | Publish version | Yes |
| POST | `/models/unpublish` | Unpublish version | Yes |

### Service Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/services/admin/create/service` | Create service (requires `modelVersion`) | Admin |
| PATCH | `/services/admin/update/service` | Update service (can change `modelVersion`) | Admin |
| PATCH | `/services/admin/update/service/version` | Switch service version | Admin |
| GET | `/services/admin/model/{model_id}/version/{version}/services` | Find services using version | Admin |
| GET | `/services/admin/model/{model_id}/deprecated-version-services` | Find services using deprecated versions | Admin |

## Additional Resources

- [API Documentation](../API_DOCUMENTATION.md)
- [Architecture Overview](../ARCHITECTURE.md)
- [Deployment Guide](../DEPLOYMENT.md)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review API error responses for detailed error messages
3. Check service logs for detailed error information
4. Contact the development team


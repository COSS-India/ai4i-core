# Model Versioning Documentation

## Overview

The Model Management Service now supports comprehensive model versioning, allowing multiple versions of the same model to coexist. Each version can have its own status (ACTIVE or DEPRECATED), and the system enforces configurable limits on the number of active versions per model.

## Key Features

### 1. Multiple Versions per Model
- The same `model_id` can have multiple versions
- Each version is uniquely identified by the combination of `(model_id, version)`
- Versions are independent entities with their own metadata and status

### 2. Version Status Management
- **ACTIVE**: Version is currently active and can be used by services
- **DEPRECATED**: Version is deprecated and should not be used for new services
- Status changes are automatically timestamped in `version_status_updated_at`

### 3. Active Version Limits
- Configurable maximum number of active versions per model (default: 5)
- Controlled via `MAX_ACTIVE_VERSIONS_PER_MODEL` environment variable
- System prevents creating new ACTIVE versions when limit is reached
- Users must deprecate existing active versions before activating new ones

### 4. Service Association
- Services must specify both `modelId` and `modelVersion` when created
- Services are associated with a specific model version
- Services can be updated to use different model versions

## Database Schema Changes

### Models Table

```sql
-- Composite unique constraint on (model_id, version)
CONSTRAINT uq_model_id_version UNIQUE (model_id, version)

-- New columns
version_status version_status NOT NULL DEFAULT 'ACTIVE'
version_status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
```

### Services Table

```sql
-- New column for model version
model_version VARCHAR(100) NOT NULL

-- Services now reference models by both model_id and model_version
```

## API Changes

### Creating Models

When creating a model, you can optionally specify the version status:

```json
{
  "modelId": "asr-model",
  "version": "1.0.0",
  "versionStatus": "ACTIVE",  // Optional, defaults to "ACTIVE"
  "name": "ASR Model",
  // ... other fields
}
```

**Behavior:**
- If `versionStatus` is not provided, it defaults to `ACTIVE`
- System checks for duplicate `(model_id, version)` combinations
- If creating as `ACTIVE`, system enforces max active versions limit
- Returns error if max active versions limit is reached

**Example Response:**
```
Model 'ASR Model' (ID: asr-model) created successfully.
```

### Updating Models

When updating a model, you **must** specify the version:

```json
{
  "modelId": "asr-model",
  "version": "1.0.0",  // Required: identifies which version to update
  "versionStatus": "DEPRECATED",  // Optional: can change status
  "name": "Updated ASR Model",  // Optional: other fields
  // ... other optional fields
}
```

**Behavior:**
- `version` field is **required** to identify which version to update
- Can update version status (ACTIVE ↔ DEPRECATED)
- When changing status to ACTIVE, system enforces max active versions limit
- `version_status_updated_at` is automatically updated when status changes

**Example Response:**
```
Model 'asr-model' updated successfully.
```

### Creating Services

Services must now specify both `modelId` and `modelVersion`:

```json
{
  "serviceId": "asr-service-1",
  "name": "ASR Service",
  "modelId": "asr-model",
  "modelVersion": "1.0.0",  // Required: specifies which model version to use
  "endpoint": "http://asr-service:8087",
  // ... other fields
}
```

**Behavior:**
- `modelVersion` is **required**
- System validates that the specified `(model_id, model_version)` combination exists
- Returns error if model version doesn't exist

**Example Response:**
```
Service 'ASR Service' (ID: asr-service-1) created successfully.
```

### Updating Services

Services can be updated to use different model versions:

```json
{
  "serviceId": "asr-service-1",
  "modelId": "asr-model",
  "modelVersion": "2.0.0",  // Optional: can update to different version
  "endpoint": "http://asr-service-v2:8087",
  // ... other optional fields
}
```

**Behavior:**
- `modelVersion` is optional in updates
- If provided, system validates the new `(model_id, model_version)` combination exists
- Service will be associated with the new model version

### Querying Models

#### Get Model by ID (with optional version)

```http
GET /models/{model_id}?version=1.0.0
```

**Behavior:**
- If `version` query parameter is provided, returns that specific version
- If `version` is not provided, returns the first matching model (for backward compatibility)
- Response includes `versionStatus` and `versionStatusUpdatedAt` fields

**Example Response:**
```json
{
  "modelId": "asr-model",
  "uuid": "123e4567-e89b-12d3-a456-426614174000",
  "name": "ASR Model",
  "version": "1.0.0",
  "versionStatus": "ACTIVE",
  "versionStatusUpdatedAt": "2024-01-15T10:30:00Z",
  // ... other fields
}
```

#### List All Models

```http
GET /models?task_type=asr
```

**Behavior:**
- Returns all model versions
- Can be filtered by `task_type`
- Each result includes version information

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Model Versioning Configuration
MAX_ACTIVE_VERSIONS_PER_MODEL=5
```

**Default:** 5 active versions per model  
**Purpose:** Limits the number of active versions that can exist simultaneously for a single model

## Migration Guide

### Running the Migration

1. **Backup your database** before running the migration

2. **Run the migration script:**
   ```bash
   psql -U dhruva_user -d model_management_db -f infrastructure/postgres/10-model-versioning-migration.sql
   ```

3. **Verify migration:**
   - Check that `version_status` column exists in `models` table
   - Check that `model_version` column exists in `services` table
   - Verify existing services have `model_version` populated

### Migration Behavior

- Existing models will have `version_status` set to `ACTIVE` by default
- Existing services will have `model_version` populated from their associated model's version
- The migration will fail if any services cannot be matched to a model version

## Best Practices

### 1. Version Naming
- Use semantic versioning (e.g., "1.0.0", "1.1.0", "2.0.0")
- Be consistent with version naming across models

### 2. Version Lifecycle
- Create new versions as `ACTIVE` when ready for production use
- Deprecate old versions before creating new ones if you've reached the limit
- Keep deprecated versions for historical reference and service compatibility

### 3. Service Management
- Always specify `modelVersion` when creating services
- Update services to new versions gradually (canary deployments)
- Monitor services using deprecated versions

### 4. Active Version Limits
- Plan ahead: deprecate old versions before creating new ones
- Use the limit to enforce version hygiene
- Adjust `MAX_ACTIVE_VERSIONS_PER_MODEL` based on your needs

## Error Handling

### Common Errors

#### 1. Duplicate Model Version
```json
{
  "status_code": 400,
  "detail": "Model with ID asr-model and version 1.0.0 already exists."
}
```
**Solution:** Use a different version string or update the existing version

#### 2. Max Active Versions Reached
```json
{
  "status_code": 400,
  "detail": "Maximum number of active versions (5) reached for model asr-model. Please deprecate an existing active version before creating a new one."
}
```
**Solution:** Deprecate an existing active version first

#### 3. Model Version Not Found (Service Creation)
```json
{
  "status_code": 400,
  "detail": "Model with ID asr-model and version 1.0.0 does not exist, cannot create service."
}
```
**Solution:** Ensure the model version exists before creating the service

#### 4. Version Required for Update
```json
{
  "status_code": 400,
  "detail": "Version is required to update a specific model version."
}
```
**Solution:** Include the `version` field in your update request

## Examples

### Example 1: Creating Multiple Versions

```bash
# Create version 1.0.0
curl -X POST http://api/models \
  -H "Content-Type: application/json" \
  -d '{
    "modelId": "asr-model",
    "version": "1.0.0",
    "versionStatus": "ACTIVE",
    "name": "ASR Model v1",
    ...
  }'

# Create version 2.0.0
curl -X POST http://api/models \
  -H "Content-Type: application/json" \
  -d '{
    "modelId": "asr-model",
    "version": "2.0.0",
    "versionStatus": "ACTIVE",
    "name": "ASR Model v2",
    ...
  }'
```

### Example 2: Deprecating an Old Version

```bash
# Deprecate version 1.0.0
curl -X PATCH http://api/models \
  -H "Content-Type: application/json" \
  -d '{
    "modelId": "asr-model",
    "version": "1.0.0",
    "versionStatus": "DEPRECATED"
  }'
```

### Example 3: Creating Service with Specific Version

```bash
curl -X POST http://api/services/admin/create/service \
  -H "Content-Type: application/json" \
  -d '{
    "serviceId": "asr-service",
    "name": "ASR Service",
    "modelId": "asr-model",
    "modelVersion": "2.0.0",
    "endpoint": "http://asr-service:8087",
    ...
  }'
```

### Example 4: Updating Service to New Version

```bash
curl -X PATCH http://api/services/admin/update/service \
  -H "Content-Type: application/json" \
  -d '{
    "serviceId": "asr-service",
    "modelId": "asr-model",
    "modelVersion": "2.0.0"
  }'
```

## API Endpoints Summary

### Model Endpoints

| Method | Endpoint | Description | Version Support |
|--------|----------|-------------|-----------------|
| POST | `/models` | Create new model version | ✅ Requires version |
| PATCH | `/models` | Update model version | ✅ Requires version |
| GET | `/models/{model_id}` | Get model (optional version) | ✅ Optional version param |
| GET | `/models` | List all models | ✅ Returns all versions |
| POST | `/models/publish` | Publish model | ⚠️ Affects all versions |
| POST | `/models/unpublish` | Unpublish model | ⚠️ Affects all versions |

### Service Endpoints

| Method | Endpoint | Description | Version Support |
|--------|----------|-------------|-----------------|
| POST | `/services/admin/create/service` | Create service | ✅ Requires modelVersion |
| PATCH | `/services/admin/update/service` | Update service | ✅ Optional modelVersion |

## Troubleshooting

### Issue: Cannot create new active version
**Cause:** Maximum active versions limit reached  
**Solution:** Deprecate an existing active version first

### Issue: Service creation fails with "model version not found"
**Cause:** The specified `(model_id, model_version)` combination doesn't exist  
**Solution:** Verify the model version exists using GET `/models/{model_id}?version={version}`

### Issue: Update model fails with "version required"
**Cause:** `version` field missing in update request  
**Solution:** Include `version` field to identify which version to update

### Issue: Migration fails
**Cause:** Services exist without matching model versions  
**Solution:** Ensure all services have valid associated models before migration

## Additional Notes

- Version status changes are automatically timestamped
- The system maintains referential integrity between services and model versions
- Cache invalidation occurs automatically when models are updated
- All version-related operations are logged for audit purposes

## Support

For issues or questions regarding model versioning, please refer to:
- Service logs: Check application logs for detailed error messages
- Database: Query `models` and `services` tables directly for debugging
- API Documentation: Use `/docs` endpoint for interactive API documentation


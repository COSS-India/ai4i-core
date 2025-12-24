# Model Versioning Feature - Changelog

## Overview

This document summarizes all changes made to implement multi-version model management in the Model Management Service.

## Version: 2.0.0 (Model Versioning Release)

### New Features

#### 1. Multi-Version Model Support
- Models can now have multiple versions (e.g., 1.0.0, 1.1.0, 2.0.0)
- Composite unique constraint on `(model_id, version)`
- Version status tracking (active/deprecated)
- Release notes for each version
- Immutability flag for published versions

#### 2. Service-Version Binding
- Services are bound to specific model versions
- Services can switch between versions of the same model
- Version update tracking with timestamps
- Impact analysis for version changes

#### 3. Version Management APIs
- Create new versions under existing models
- List all versions of a model
- Deprecate versions
- Filter models by version status
- Get services using specific versions
- Find services using deprecated versions

#### 4. Configuration Management
- Configurable active version limits
- Immutability enforcement toggle
- Deprecated version usage policies
- Warning system for deprecated version usage

### Database Changes

#### Models Table
- **Added Columns:**
  - `version_status` (VARCHAR(50), default: 'active')
  - `release_notes` (TEXT)
  - `is_immutable` (BOOLEAN, default: false)
  
- **Modified Constraints:**
  - Removed unique constraint from `model_id`
  - Added composite unique constraint on `(model_id, version)`
  
- **New Indexes:**
  - `idx_model_id_version` on `(model_id, version)`
  - `idx_model_id_version_status` on `(model_id, version_status)`

#### Services Table
- **Added Columns:**
  - `model_version` (VARCHAR(100), NOT NULL)
  - `version_updated_at` (BIGINT)
  
- **New Indexes:**
  - `idx_service_model_version` on `(model_id, model_version)`

### New Files

#### Models
- `models/model_version.py` - Pydantic models for version operations

#### Repositories
- `repositories/model_repository.py` - Version-aware model repository

#### Services
- `services/version_service.py` - Version management business logic
- `services/service_version_service.py` - Service-version operations

#### Middleware
- `middleware/permissions.py` - Role-based permission checking

#### Configuration
- `config.py` - Centralized configuration management

#### Documentation
- `docs/MODEL_VERSIONING.md` - Comprehensive documentation
- `docs/VERSIONING_QUICK_REFERENCE.md` - Quick reference guide
- `docs/VERSIONING_CHANGELOG.md` - This file

#### Migrations
- `migrations/add_model_versioning.sql` - Database migration script

### Modified Files

#### Models
- `models/db_models.py` - Added version fields and constraints
- `models/model_create.py` - Added `releaseNotes`, `versionStatus`, validators
- `models/model_view.py` - Added version-related response fields
- `models/model_update.py` - Added `releaseNotes`, version validation
- `models/service_create.py` - Added required `modelVersion` field
- `models/service_view.py` - Added `modelVersion`, `availableVersions`
- `models/service_update.py` - Added `modelVersion` for version switching
- `models/service_list.py` - Inherits `modelVersion` from `ServiceResponse`

#### Database Operations
- `db_operations.py` - Major updates:
  - Version-aware model operations
  - Service version validation
  - Version-specific cache keys
  - New functions: `create_model_version`, `get_model_versions`, `deprecate_model_version`
  - Updated: `save_model_to_db`, `update_model`, `get_model_details`, `list_all_models`
  - Updated: `save_service_to_db`, `update_service`, `get_service_details`, `list_all_services`

#### Routers
- `routers/router_restful.py`:
  - Added `GET /models/{model_id}/versions`
  - Added `POST /models/{model_id}/versions`
  - Added `PATCH /models/{model_id}/versions/{version}/deprecate`
  - Updated endpoints to support version query parameters
  - Added version status filtering
  
- `routers/router_admin.py`:
  - Added `POST /services/admin/create/model/{model_id}/version`
  - Added `PATCH /services/admin/deprecate/model/version`
  - Added `GET /services/admin/model/{model_id}/versions`
  - Added `GET /services/admin/model/{model_id}/version/{version}/services`
  - Added `GET /services/admin/model/{model_id}/deprecated-version-services`
  - Added `PATCH /services/admin/update/service/version`
  - Updated publish/unpublish to support versions

#### Middleware
- `middleware/exceptions.py` - Added version-related exceptions:
  - `VersionAlreadyExistsError`
  - `VersionNotFoundError`
  - `ImmutableVersionError`
  - `ActiveVersionLimitExceededError`
  - `InvalidVersionFormatError`
  - `DeprecatedVersionError`
  - `ServiceVersionSwitchError`

- `middleware/error_handler_middleware.py` - Added error handlers for new exceptions

#### Configuration
- `env.template` - Added version management configuration:
  - `MAX_ACTIVE_VERSIONS_PER_MODEL=5`
  - `DEFAULT_VERSION_STATUS=active`
  - `ENABLE_VERSION_IMMUTABILITY=true`
  - `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH=false`
  - `WARN_ON_DEPRECATED_VERSION_USAGE=true`

### Breaking Changes

#### API Changes
1. **Model Creation**: Now requires `version` field (was optional, now required)
2. **Model Updates**: Now requires `version` field to identify which version to update
3. **Service Creation**: Now requires `modelVersion` field
4. **Model Uniqueness**: `model_id` is no longer unique; uniqueness is on `(model_id, version)`

#### Database Changes
1. **Migration Required**: Must run migration script before deploying
2. **Existing Services**: Will be migrated to use `model_version` column
3. **Cache Keys**: Changed from `model:{model_id}` to `model:{model_id}:{version}`

### Migration Steps

1. **Backup Database**
   ```bash
   pg_dump -U dhruva_user -d model_management_db > backup.sql
   ```

2. **Run Migration Script**
   ```bash
   psql -U dhruva_user -d model_management_db -f migrations/add_model_versioning.sql
   ```

3. **Deploy Updated Code**
   - Deploy new service version
   - Restart service

4. **Verify Migration**
   - Check database schema
   - Test API endpoints
   - Verify existing data

### Backward Compatibility

#### Maintained
- Existing API endpoints still work (with version parameters)
- Existing data is migrated automatically
- Cache structure is backward compatible (new keys, old keys still work)

#### Not Maintained
- Direct database queries assuming `model_id` uniqueness
- Cache lookups using old key format (will miss, but won't error)
- Services without `model_version` (migration sets default)

### Performance Considerations

#### Improvements
- Indexed queries on `(model_id, version)` for faster lookups
- Composite indexes for efficient filtering
- Version-specific cache keys reduce cache conflicts

#### Potential Impact
- Slightly larger database (additional columns)
- More complex queries (joins on composite keys)
- Cache key changes may cause initial cache misses

### Security Updates

- Added Moderator role requirement for version management operations
- Permission checks for version creation, deprecation
- Validation of version formats and status transitions

### Testing Recommendations

1. **Unit Tests**
   - Version creation and validation
   - Service version switching
   - Immutability checks
   - Active version limit enforcement

2. **Integration Tests**
   - API endpoint functionality
   - Database migration
   - Cache operations
   - Service-model version relationships

3. **End-to-End Tests**
   - Complete version lifecycle
   - Service migration scenarios
   - Rollback procedures

### Known Limitations

1. **Composite Foreign Keys**: SQLAlchemy doesn't fully support composite foreign keys, so validation is done at application level
2. **Cache Migration**: Old cache entries may need manual cleanup
3. **Version Format**: Currently only semantic versioning pattern is enforced

### Future Enhancements

Potential improvements for future releases:
- Version comparison and diff functionality
- Automated version deprecation policies
- Version rollback automation
- Version performance metrics
- A/B testing support for versions
- Version approval workflows

### Support

For issues or questions:
- See `docs/MODEL_VERSIONING.md` for detailed documentation
- See `docs/VERSIONING_QUICK_REFERENCE.md` for quick reference
- Check API error responses for detailed error messages
- Review service logs for debugging information


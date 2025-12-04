# Analysis: `key_name` and `last_used` Fields

## Purpose

### `key_name` (or `name`)
- **Purpose**: User-friendly label/identifier for an API key
- **Usage**: 
  - Displayed in UI when listing API keys
  - Used for identification and management
  - Stored in database as a descriptive name
- **Example**: "Production API Key", "Test Key", "Mobile App Key"

### `last_used` (or `last_used_at`)
- **Purpose**: Tracks when an API key was last used for authentication
- **Usage**:
  - Security monitoring (identify unused keys)
  - Usage analytics
  - Automatic cleanup of inactive keys
  - Updated every time the API key is validated/used
- **Example**: `2024-01-15T10:30:00Z`

## Current Naming Inconsistency

### Database Schema
```sql
CREATE TABLE api_keys (
    ...
    name VARCHAR(100) NOT NULL,              -- Column name: "name"
    last_used_at TIMESTAMP WITH TIME ZONE    -- Column name: "last_used_at"
);
```

### Code Usage (Inconsistent)

#### Auth Service (`services/auth-service/models.py`)
```python
class APIKey(Base):
    key_name = Column(String(100), nullable=False)      # Maps to DB column "name"?
    last_used = Column(DateTime(timezone=True))         # Maps to DB column "last_used_at"?
```
**⚠️ ISSUE**: Model uses `key_name` and `last_used` but database has `name` and `last_used_at`

#### ASR Service (`services/asr-service/models/auth_models.py`)
```python
class ApiKeyDB(Base):
    name = Column(String(100), nullable=False)         # ✅ Matches DB column "name"
    last_used_at = Column(DateTime(timezone=True))     # ✅ Matches DB column "last_used_at"
```
**✅ CORRECT**: Matches database column names

#### Model Management Service (`services/model-management-service/models/auth_models.py`)
```python
class ApiKeyDB(AuthDBBase):
    key_name = Column(String(100), nullable=True)       # Maps to DB column "name"?
    last_used = Column(DateTime(timezone=True))        # Maps to DB column "last_used_at"?
    
    # Compatibility properties
    @property
    def name(self):
        return self.key_name
    
    @property
    def last_used_at(self):
        return self.last_used
```
**⚠️ ISSUE**: Uses `key_name`/`last_used` but has compatibility properties

## Impact of Renaming

### If Renaming Database Columns

**From**: `name`, `last_used_at`  
**To**: `key_name`, `last_used`

**Required Changes**:
1. ✅ **Database Migration**: ALTER TABLE statements
2. ✅ **Update All Models**: Remove column name mappings, use direct names
3. ✅ **Update All Repositories**: Change SQL queries using these columns
4. ✅ **Update Frontend**: If API responses change
5. ✅ **Update Documentation**: API docs, schemas

**Affected Files**:
- `infrastructure/postgres/01-auth-schema.sql`
- `infrastructure/postgres/init-all-databases.sql`
- All service models in `services/*/models/auth_models.py`
- All repositories in `services/*/repositories/api_key_repository.py`
- `services/auth-service/models.py`
- `frontend/simple-ui/src/types/auth.ts`

### If Renaming Code Only (Adding Column Mappings)

**Option**: Keep database as `name`/`last_used_at`, map in SQLAlchemy

**Required Changes**:
```python
class APIKey(Base):
    key_name = Column(String(100), nullable=False, name='name')  # Map to DB column 'name'
    last_used = Column(DateTime(timezone=True), name='last_used_at')  # Map to DB column 'last_used_at'
```

**Affected Files**:
- `services/auth-service/models.py`
- `services/model-management-service/models/auth_models.py`
- Any other services using `key_name`/`last_used`

## Recommendations

### Option 1: Standardize on Database Names (Recommended)
- **Use**: `name` and `last_used_at` everywhere
- **Pros**: 
  - Matches database schema
  - No column mappings needed
  - Consistent with most services
- **Cons**: 
  - Need to update auth-service and model-management-service
  - `name` is less descriptive than `key_name`

### Option 2: Standardize on Code Names
- **Use**: `key_name` and `last_used` everywhere
- **Pros**:
  - More descriptive (`key_name` vs `name`)
  - Consistent with auth-service API
- **Cons**:
  - Requires database migration
  - Need column mappings or schema change
  - More disruptive

### Option 3: Keep Compatibility Properties (Current State)
- **Use**: Both naming conventions with compatibility properties
- **Pros**:
  - Backward compatible
  - Works with both naming styles
- **Cons**:
  - Confusing and error-prone
  - Maintenance burden
  - Inconsistent codebase

## Current Usage Locations

### `key_name` / `name` Usage:
- API key creation endpoints
- API key listing endpoints
- Frontend display
- Middleware authentication providers
- Kong configuration files

### `last_used` / `last_used_at` Usage:
- Updated in `update_last_used()` repository methods
- Updated in `validate_api_key()` functions
- Displayed in API responses
- Used for analytics and monitoring

## Critical Impact Areas

1. **Database Operations**: Any rename requires migration
2. **API Contracts**: Frontend and external clients depend on field names
3. **Repository Methods**: All `update_last_used()` methods need updates
4. **Model Definitions**: All SQLAlchemy models need updates
5. **Type Definitions**: TypeScript types in frontend need updates

## Conclusion

**Current State**: There is a naming inconsistency that could cause database errors if SQLAlchemy models don't have explicit column mappings.

**Recommendation**: Standardize on `name` and `last_used_at` to match the database schema, and update auth-service and model-management-service to use these names consistently.



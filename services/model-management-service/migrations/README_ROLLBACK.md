# Database Rollback Guide

This directory contains scripts to rollback the model versioning feature changes.

## ⚠️ WARNING

**Rolling back will cause data loss:**
- Multiple versions of the same model will be consolidated into a single version
- Only the latest active version (or first version) will be kept per model
- All version history, release notes, and version status will be lost
- Service version tracking will be removed

## Rollback Procedure

### Step 1: Backup Your Data

**Option A: Full Database Backup (Recommended)**
```bash
pg_dump -U dhruva_user -d model_management_db > backup_before_rollback_$(date +%Y%m%d_%H%M%S).sql
```

**Option B: Export Version Data Only**
```bash
psql -U dhruva_user -d model_management_db -f export_version_data_before_rollback.sql
```

This creates backup tables:
- `models_version_backup` - All model versions
- `services_version_backup` - Service version mappings
- `model_version_keep_mapping` - Shows which versions will be kept

### Step 2: Review What Will Be Lost

Run the verification queries in `export_version_data_before_rollback.sql` to see:
- Which model versions will be kept vs deleted
- Which services will be affected
- Version mappings that will be lost

### Step 3: Export Important Data (Optional)

If you need to preserve specific versions, export them:

```sql
-- Export specific model versions
SELECT * FROM models_version_backup 
WHERE model_id = 'your-model-id' 
INTO '/tmp/model_versions.csv' CSV HEADER;

-- Export service mappings
SELECT * FROM services_version_backup 
INTO '/tmp/service_mappings.csv' CSV HEADER;
```

### Step 4: Run Rollback Script

```bash
psql -U dhruva_user -d model_management_db -f rollback_model_versioning.sql
```

### Step 5: Verify Rollback

Run the verification queries at the end of `rollback_model_versioning.sql`:

```sql
-- Check table structure
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'models' 
ORDER BY ordinal_position;

-- Verify model_id uniqueness
SELECT model_id, COUNT(*) 
FROM models 
GROUP BY model_id 
HAVING COUNT(*) > 1;
-- Should return no rows

-- Check for orphaned services
SELECT s.service_id, s.model_id 
FROM services s
LEFT JOIN models m ON s.model_id = m.model_id
WHERE m.model_id IS NULL;
-- Should return no rows
```

## What Gets Rolled Back

### Removed Columns

**Models Table:**
- `version_status`
- `release_notes`
- `is_immutable`

**Services Table:**
- `model_version`
- `version_updated_at`

### Removed Constraints

- Composite unique constraint `uq_model_id_version`
- Restored unique constraint on `model_id` only

### Removed Indexes

- `idx_model_id_version`
- `idx_model_id_version_status`
- `idx_service_model_version`

### Data Consolidation

- Multiple versions of the same model → Single version kept
- Keeps latest active version (or first version if none active)
- Services updated to reference consolidated models

## Restoring After Rollback

If you need to restore specific data after rollback:

### Restore a Model Version

```sql
-- First, you'll need to remove the unique constraint temporarily
ALTER TABLE models DROP CONSTRAINT models_model_id_key;

-- Insert the version you want to restore
INSERT INTO models (
    id, model_id, version, name, description, ...
)
SELECT 
    id, model_id, version, name, description, ...
FROM models_version_backup
WHERE model_id = 'your-model-id' AND version = 'your-version';

-- Re-add unique constraint (will fail if duplicates exist)
ALTER TABLE models ADD CONSTRAINT models_model_id_key UNIQUE (model_id);
```

### Restore Service Version Mapping

After restoring model versions, you can update services:

```sql
UPDATE services s
SET model_id = (
    SELECT model_id 
    FROM services_version_backup svb 
    WHERE svb.service_id = s.service_id
)
WHERE EXISTS (
    SELECT 1 FROM services_version_backup svb 
    WHERE svb.service_id = s.service_id
);
```

## Cleanup After Rollback

Once you've verified the rollback and don't need the backups:

```sql
DROP TABLE IF EXISTS models_version_backup;
DROP TABLE IF EXISTS services_version_backup;
DROP TABLE IF EXISTS model_version_keep_mapping;
```

## Troubleshooting

### Error: "Cannot add unique constraint: duplicate model_ids exist"

This means the consolidation step didn't work correctly. Check:

```sql
-- Find duplicate model_ids
SELECT model_id, COUNT(*) 
FROM models 
GROUP BY model_id 
HAVING COUNT(*) > 1;

-- Manually delete duplicates, keeping the one you want
DELETE FROM models 
WHERE id = 'duplicate-id-to-remove';
```

### Error: "Services reference non-existent models"

This means some services point to models that were deleted. Fix:

```sql
-- Find orphaned services
SELECT s.* 
FROM services s
LEFT JOIN models m ON s.model_id = m.model_id
WHERE m.model_id IS NULL;

-- Either delete these services or update them to reference valid models
DELETE FROM services 
WHERE model_id NOT IN (SELECT model_id FROM models);
```

### Rollback Partially Completed

If rollback fails partway through:

1. Check transaction status: `SELECT * FROM pg_stat_activity WHERE state = 'active';`
2. If in a failed transaction, rollback: `ROLLBACK;`
3. Check current state of tables
4. Re-run rollback script (it's idempotent - safe to run multiple times)

## Alternative: Selective Rollback

If you only want to remove versioning features but keep all versions:

1. **Don't run the full rollback script**
2. Instead, manually:
   - Remove version columns but keep all model records
   - Update application code to ignore version fields
   - Keep services as-is (they'll just ignore model_version column)

This approach keeps all data but removes version management features.

## Questions?

- Check the main documentation: `docs/MODEL_VERSIONING.md`
- Review the rollback script comments
- Check database logs for detailed error messages


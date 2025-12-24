# Model Versioning Quick Reference

## Common Operations

### Create New Model Version
```bash
curl -X POST "http://localhost:8091/models/{model_id}/versions" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.1.0",
    "releaseNotes": "Performance improvements",
    "versionStatus": "active"
  }'
```

### List All Versions
```bash
curl -X GET "http://localhost:8091/models/{model_id}/versions" \
  -H "Authorization: Bearer <token>"
```

### Get Specific Version
```bash
curl -X GET "http://localhost:8091/models/{model_id}?version=1.1.0" \
  -H "Authorization: Bearer <token>"
```

### Deprecate Version
```bash
curl -X PATCH "http://localhost:8091/models/{model_id}/versions/1.0.0/deprecate" \
  -H "Authorization: Bearer <token>"
```

### Switch Service Version
```bash
curl -X PATCH "http://localhost:8091/services/admin/update/service/version?service_id={service_id}&new_version=1.1.0"
```

### Find Services Using Deprecated Versions
```bash
curl -X GET "http://localhost:8091/services/admin/model/{model_id}/deprecated-version-services"
```

## Version Status Flow

```
[Create] → active → [Publish] → active (immutable) → [Deprecate] → deprecated
```

## Key Constraints

- ✅ Multiple versions per model allowed
- ✅ Unique constraint on `(model_id, version)`
- ✅ Max 5 active versions per model (configurable)
- ✅ Published versions become immutable (configurable)
- ✅ Services bound to specific versions
- ❌ Cannot modify immutable versions
- ❌ Cannot use deprecated versions for new services (configurable)

## Configuration Checklist

- [ ] Set `MAX_ACTIVE_VERSIONS_PER_MODEL`
- [ ] Configure `ENABLE_VERSION_IMMUTABILITY`
- [ ] Set `ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH` policy
- [ ] Run database migration script
- [ ] Update service code
- [ ] Test version creation
- [ ] Test service version switching

## Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 409 | Version already exists | Use different version number |
| 400 | Active version limit exceeded | Deprecate old versions |
| 403 | Version is immutable | Create new version instead |
| 404 | Version not found | Check available versions |
| 400 | Deprecated version | Re-activate or allow deprecated versions |

## Version Naming Convention

Use semantic versioning: `MAJOR.MINOR.PATCH`

- **1.0.0** - Initial release
- **1.1.0** - New features (backward compatible)
- **1.1.1** - Bug fixes
- **2.0.0** - Breaking changes


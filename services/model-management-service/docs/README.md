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
2. **Run Migration**: Execute `infrastructure/postgres/10-model-versioning-migration.sql` for versioning support
3. **Start Service**: Use Docker Compose or run directly with `python main.py`

## Key Features

- ✅ Model versioning with status management
- ✅ Configurable active version limits
- ✅ Service-to-version association
- ✅ RESTful API endpoints
- ✅ Redis caching support
- ✅ Authentication and authorization

## Support

For issues or questions, refer to:
- Service logs
- API documentation at `/docs`
- Database schema in `models/db_models.py`


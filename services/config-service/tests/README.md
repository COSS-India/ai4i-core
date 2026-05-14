# Config Service Tests

Test suite for the configuration management service.

## Test Coverage

1. **ConfigurationRepository Tests** - CRUD, versioning, audit history
2. **ServiceRegistryRepository Tests** - Registration, deregistration, health checks
3. **ConfigService Tests** - Cache behavior, Kafka event publishing, bulk operations
4. **API Endpoint Tests** - REST endpoints, request validation, error handling
5. **Integration Tests** - End-to-end flows, cache invalidation, graceful degradation

## Prerequisites

1. **PostgreSQL** - Test database (default: `config_db_test`)
2. **Redis** - Test cache (default: database 2)
3. **Python Dependencies**:
   ```bash
   pip install pytest pytest-asyncio pytest-cov
   ```

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html --cov-report=term

# Integration tests only
pytest tests/ -m integration -v

# Unit tests only
pytest tests/ -m "not integration" -v
```

## Environment Variables

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/config_db_test"
export TEST_REDIS_URL="redis://localhost:6379/2"
```

## Test Structure

```
tests/
├── conftest.py        # Shared fixtures and test configuration
├── test_config.py     # Configuration management tests
├── test_registry.py   # Service registry tests
├── run_tests.sh       # Test runner script
└── README.md          # This file
```

## Mocking Strategy

- **Kafka Producer**: Mocked to avoid requiring Kafka broker
- **Database**: Uses real PostgreSQL (test database) for integration testing
- **Redis**: Uses real Redis (test database) for cache testing

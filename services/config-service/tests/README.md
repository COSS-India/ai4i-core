# Feature Flag Tests

Comprehensive test suite for feature flag functionality with Unleash and OpenFeature integration.

## Test Coverage

The test suite covers:

1. **UnleashFeatureProvider Tests**
   - Provider initialization
   - Boolean, string, integer, float, and object flag evaluation
   - Error handling and fallback behavior
   - Context mapping from OpenFeature to Unleash

2. **FeatureFlagRepository Tests**
   - CRUD operations (Create, Read, Update, Delete)
   - Evaluation history recording
   - Pagination support
   - Flag statistics tracking

3. **FeatureFlagService Tests**
   - All flag type evaluations (boolean, string, integer, float, object)
   - Cache behavior (hit/miss, invalidation)
   - Bulk evaluation
   - Kafka event publishing
   - Error handling and fallback

4. **API Endpoint Tests**
   - All REST endpoints
   - Request validation
   - Response formatting
   - Error handling

5. **Integration Tests**
   - End-to-end evaluation flow
   - Cache invalidation on updates
   - Multiple flag type evaluation
   - Graceful degradation when services unavailable

## Prerequisites

1. **PostgreSQL** - Test database (default: `config_db_test`)
2. **Redis** - Test cache (default: database 2)
3. **Python Dependencies**:
   ```bash
   pip install pytest pytest-asyncio pytest-cov
   ```

## Running Tests

### Run All Tests

```bash
# From config-service directory
pytest tests/test_feature_flags.py -v
```

### Run Specific Test Classes

```bash
# Test provider only
pytest tests/test_feature_flags.py::TestUnleashFeatureProvider -v

# Test repository only
pytest tests/test_feature_flags.py::TestFeatureFlagRepository -v

# Test service only
pytest tests/test_feature_flags.py::TestFeatureFlagService -v

# Test API endpoints only
pytest tests/test_feature_flags.py::TestAPIEndpoints -v
```

### Run with Coverage

```bash
pytest tests/test_feature_flags.py --cov=. --cov-report=html --cov-report=term
```

### Run Integration Tests Only

```bash
pytest tests/test_feature_flags.py -m integration -v
```

### Run Unit Tests Only

```bash
pytest tests/test_feature_flags.py -m "not integration" -v
```

## Environment Variables

Set these environment variables to configure test database and Redis:

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/config_db_test"
export TEST_REDIS_URL="redis://localhost:6379/2"
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── test_feature_flags.py    # Comprehensive test suite
├── run_tests.sh            # Test runner script
└── README.md               # This file
```

## Fixtures

The test suite uses the following key fixtures (defined in `conftest.py`):

- `test_db_session` - Async database session with automatic cleanup
- `redis_client` - Redis client with test database
- `mock_kafka_producer` - Mocked Kafka producer
- `mock_unleash_client` - Mocked Unleash client
- `mock_openfeature_client` - Mocked OpenFeature client
- `feature_flag_repository` - Repository instance
- `feature_flag_service` - Service instance with mocked dependencies
- `unleash_provider` - Unleash provider instance
- `test_app` - FastAPI application instance
- `test_client` - FastAPI test client

## Mocking Strategy

- **Unleash Client**: Mocked to avoid requiring actual Unleash server
- **OpenFeature Client**: Mocked with predefined responses for different flag types
- **Kafka Producer**: Mocked to avoid requiring Kafka broker
- **Database**: Uses real PostgreSQL (test database) for integration testing
- **Redis**: Uses real Redis (test database) for cache testing

## Test Data

Tests create and clean up their own data:
- Feature flags are created in test database
- Evaluations are recorded in test database
- Cache entries are stored in test Redis database
- All test data is cleaned up after each test

## Troubleshooting

### Database Connection Issues

If tests fail with database connection errors:
1. Ensure PostgreSQL is running
2. Check `TEST_DATABASE_URL` environment variable
3. Verify database `config_db_test` exists
4. Check user permissions

### Redis Connection Issues

If tests fail with Redis connection errors:
1. Ensure Redis is running
2. Check `TEST_REDIS_URL` environment variable
3. Verify Redis database 2 is available

### Import Errors

If you see import errors:
1. Ensure you're running tests from the `config-service` directory
2. Check that all dependencies are installed: `pip install -r requirements.txt`
3. Verify Python path includes the service directory

## Continuous Integration

These tests are designed to run in CI/CD pipelines. Set the following environment variables:

```yaml
TEST_DATABASE_URL: postgresql+asyncpg://user:pass@postgres:5432/config_db_test
TEST_REDIS_URL: redis://redis:6379/2
```

## Next Steps

After running tests successfully:
1. Review coverage report to identify untested code paths
2. Add tests for edge cases specific to your use case
3. Consider adding performance/load tests for high-traffic scenarios
4. Add tests for Unleash sync functionality with actual Unleash server


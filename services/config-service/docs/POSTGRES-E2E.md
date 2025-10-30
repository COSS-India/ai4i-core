## PostgreSQL in Config Service: End-to-End Overview

This document explains how PostgreSQL is used by the Config Service across configuration management, feature flags, and the service registry. It covers schema, connection, read/write flows, caching, and failure handling.

### 1) What PostgreSQL stores
- Configuration key/values with per-service and per-environment scoping.
- Historical changes for audit/versioning.
- Feature flags with targeting and rollout metadata.
- A persistent view of the service registry (service URL, health status, metadata, timestamps).

### 2) Schema (SQLAlchemy models)
Defined in `services/config-service/models/database_models.py`:

```20:36:services/config-service/models/database_models.py
class Configuration(Base):
    __tablename__ = "configurations"
    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    environment = Column(String(50), nullable=False)
    service_name = Column(String(100), nullable=False)
    is_encrypted = Column(Boolean, default=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
```

```39:54:services/config-service/models/database_models.py
class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    is_enabled = Column(Boolean, default=False)
    rollout_percentage = Column(String)
    target_users = Column(JSON)
    environment = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
```

```56:71:services/config-service/models/database_models.py
class ServiceRegistry(Base):
    __tablename__ = "service_registry"
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False, unique=True)
    service_url = Column(String(255), nullable=False)
    health_check_url = Column(String(255))
    status = Column(String(20), default="unknown")
    last_health_check = Column(DateTime(timezone=True))
    service_metadata = Column(JSON)
    registered_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
```

```73:86:services/config-service/models/database_models.py
class ConfigurationHistory(Base):
    __tablename__ = "configuration_history"
    id = Column(Integer, primary_key=True)
    configuration_id = Column(Integer, ForeignKey("configurations.id", ondelete="CASCADE"))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_by = Column(String(100))
    changed_at = Column(DateTime(timezone=True))
```

Tables are auto-created on startup: see `main.py` where `Base.metadata.create_all` runs inside an async engine context.

```57:74:services/config-service/main.py
database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://dhruva_user:...@postgres:5432/config_db')
db_engine = create_async_engine(database_url, pool_size=10, max_overflow=5, echo=False)
db_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
```

### 3) Connection configuration
- Env var `DATABASE_URL` (asyncpg) controls the connection string.
- Defaults to the in-docker Postgres service (`postgres:5432/config_db`).
- Connection pool sizing is set via `pool_size` and `max_overflow` in `create_async_engine`.

### 4) Read/Write flows

- Configurations
  - Create: `ConfigRepository.create_configuration(...)` inserts into `configurations` and an entry into `configuration_history` in a single transaction.
  - Read: `ConfigRepository.get_configuration(...)` and list APIs query by `key`, `environment`, `service_name`.
  - Update/Delete: repository methods use `update`/`delete` with version and timestamp updates.

- Feature Flags
  - Create/Update/List implemented in `feature_flag_repository.py` with similar patterns.
  - Stores targeting (`target_users`) and rollout percentage.

- Service Registry (persistent state)
  - On registration API: `ServiceRegistryService.register_service(...)` writes/updates the `service_registry` row via `ServiceRegistryRepository.register_service(...)`.
  - On health checks: `ServiceRegistryService.perform_health_check(...)` updates the `status` and optionally `last_health_check`.
  - Listing: `ServiceRegistryRepository.list_services(...)` returns all rows with optional status filter.

### 5) Interaction with Redis and ZooKeeper
- ZooKeeper: Source of truth for live service instances and watch events (see `registry/zookeeper_client.py`).
- PostgreSQL: System of record for registry state, health status, and historical changes (persistent, queryable, auditable).
- Redis: Short-lived cache used by `ServiceRegistryService` for instance lists to reduce round-trips and accelerate discovery.

Flow summary for registry:
1. Service POSTs to `/api/v1/registry/register`.
2. ZooKeeper is updated (live registry) and an instance_id is returned.
3. PostgreSQL `service_registry` row is upserted as healthy with URLs and metadata.
4. Redis cache for that service’s instances is invalidated.

### 6) API surfaces touching PostgreSQL
- Config endpoints: `routers/config_router.py` → `ConfigurationService` → `ConfigRepository` → PostgreSQL.
- Feature flag endpoints: `routers/feature_flag_router.py` → `FeatureFlagService` → repository → PostgreSQL.
- Registry endpoints: `routers/service_registry_router.py` → `ServiceRegistryService` → `ServiceRegistryRepository` → PostgreSQL.

### 7) Startup & lifecycle
- On service startup (`@app.on_event("startup")` in `main.py`):
  - Connect to Redis, PostgreSQL; create tables; attempt to start Kafka producer (optional).
  - Initialize ZooKeeper client for registry operations.

### 8) Failure modes & behavior
- PostgreSQL unavailable at startup: service fails early after logging an error during engine init or table creation.
- PostgreSQL unavailable during requests: repository methods catch, rollback, and propagate errors; callers return 5xx.
- ZooKeeper available but PostgreSQL down: registry updates in ZooKeeper succeed, but persistence will fail; cache may still be invalidated; subsequent list APIs may return stale or partial data.

### 9) Operations
- Backups: dump `configurations`, `feature_flags`, `service_registry`, and `configuration_history` for DR/audit.
- Migrations: Model changes require Alembic or equivalent; currently tables are auto-created if missing.
- Tuning: Adjust `pool_size`, `max_overflow`, and Postgres resources under load.

### 10) Quick reference
- Connection string: `DATABASE_URL` (asyncpg)
- Models: `services/config-service/models/database_models.py`
- Repos: `services/config-service/repositories/*.py`
- Entry: `services/config-service/main.py`
- Registry service logic: `services/config-service/services/service_registry_service.py`



# 🚀 AI4I Core - Database Migration Framework

A **Laravel-like** unified database migration system that works consistently across **PostgreSQL, Redis, InfluxDB, Elasticsearch, and Kafka**.

---

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Running Migrations](#running-migrations)
  - [Rolling Back Migrations](#rolling-back-migrations)
  - [Migration Status](#migration-status)
  - [Fresh Migrations](#fresh-migrations)
  - [Creating Migrations](#creating-migrations)
  - [Running Seeders](#running-seeders)
- [Database Adapters](#database-adapters)
- [Writing Migrations](#writing-migrations)
- [Writing Seeders](#writing-seeders)
- [Configuration](#configuration)
- [Examples](#examples)

---

## ✨ Features

✅ **Unified Interface** - Single CLI for all databases  
✅ **5 Database Types** - PostgreSQL, Redis, InfluxDB, Elasticsearch, Kafka  
✅ **Version Control** - Track migrations across all databases  
✅ **Rollback Support** - Safely undo changes  
✅ **Batch Management** - Group and rollback migrations together  
✅ **Seeders** - Populate databases with test data  
✅ **Auto-generation** - Create migration templates automatically  
✅ **Python Native** - Integrates with your FastAPI/Python stack  
✅ **Laravel-like** - Familiar commands and workflow  

---

## 🏗️ Architecture

```
infrastructure/migrations/
├── core/                          # Core framework
│   ├── base_adapter.py           # Abstract adapter interface
│   ├── base_migration.py         # Base migration class
│   ├── base_seeder.py            # Base seeder class
│   ├── migration_manager.py      # Migration orchestration
│   └── version_tracker.py        # Version tracking logic
│
├── adapters/                      # Database-specific implementations
│   ├── postgres_adapter.py       # PostgreSQL adapter
│   ├── redis_adapter.py          # Redis adapter
│   ├── influxdb_adapter.py       # InfluxDB adapter
│   ├── elasticsearch_adapter.py  # Elasticsearch adapter
│   └── kafka_adapter.py          # Kafka adapter
│
├── migrations/                    # Migration files
│   ├── postgres/
│   │   └── 2024_02_15_000001_create_example_table.py
│   ├── redis/
│   │   └── 2024_02_15_000001_setup_cache_structure.py
│   ├── influxdb/
│   │   └── 2024_02_15_000001_create_metrics_bucket.py
│   ├── elasticsearch/
│   │   └── 2024_02_15_000001_create_logs_index.py
│   └── kafka/
│       └── 2024_02_15_000001_create_event_topics.py
│
├── seeders/                       # Seeder files
│   ├── postgres/
│   │   └── default_data_seeder.py
│   ├── redis/
│   │   └── cache_warmup_seeder.py
│   └── influxdb/
│       └── sample_metrics_seeder.py
│
├── cli.py                         # Command-line interface
├── config.py                      # Database configurations
└── requirements.txt               # Python dependencies
```

---

## 📦 Installation

### 1. Install Dependencies

```bash
cd infrastructure/migrations
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Verify Installation

```bash
python cli.py migrate:status
```

---

## 🚀 Quick Start

### Run All Migrations

```bash
# Migrate all databases
python cli.py migrate

# Migrate specific database
python cli.py migrate --database postgres
python cli.py migrate --database redis
```

### Check Status

```bash
# Check all databases
python cli.py migrate:status

# Check specific database
python cli.py migrate:status --database postgres
```

### Create New Migration

```bash
python cli.py make:migration create_users_table --database postgres
```

### Run Seeders

```bash
python cli.py seed --database postgres
```

---

## 📖 Usage

### Running Migrations

**Migrate all databases:**
```bash
python cli.py migrate
```

**Migrate specific database:**
```bash
python cli.py migrate --database postgres
python cli.py migrate --database redis
python cli.py migrate --database influxdb
python cli.py migrate --database elasticsearch
python cli.py migrate --database kafka
```

**For PostgreSQL, specify which database:**
```bash
python cli.py migrate --database postgres --postgres-db auth_db
python cli.py migrate --database postgres --postgres-db config_db
python cli.py migrate --database postgres --postgres-db model_management_db
```

**Run specific number of migrations:**
```bash
python cli.py migrate --database postgres --steps 3
```

---

### Rolling Back Migrations

**Rollback last batch:**
```bash
python cli.py rollback --database postgres
```

**Rollback multiple batches:**
```bash
python cli.py rollback --database postgres --steps 2
```

---

### Migration Status

**Check all databases:**
```bash
python cli.py migrate:status
```

**Output:**
```
📊 POSTGRES Migration Status:
================================================================================
  ✅ Executed - 2024_02_15_000001_create_example_table.py
  ⏳ Pending  - 2024_02_15_000002_add_metadata_column.py
================================================================================

📊 REDIS Migration Status:
================================================================================
  ✅ Executed - 2024_02_15_000001_setup_cache_structure.py
================================================================================
```

---

### Fresh Migrations

**Drop all and re-run:**
```bash
python cli.py migrate:fresh --database postgres
```

**With seeders:**
```bash
python cli.py migrate:fresh --seed --database postgres
```

⚠️ **WARNING:** This will **DELETE ALL DATA** in the database!

---

### Creating Migrations

**Auto-generate migration file:**
```bash
python cli.py make:migration create_users_table --database postgres
```

**Output:**
```
✅ Created migration: infrastructure/migrations/migrations/postgres/2024_02_15_120530_create_users_table.py
```

The generated file will look like:
```python
from infrastructure.migrations.core.base_migration import BaseMigration

class CreateUsersTable(BaseMigration):
    """Migration: create users table"""
    
    def up(self, adapter):
        """Run migration"""
        # TODO: Implement migration logic
        pass
    
    def down(self, adapter):
        """Rollback migration"""
        # TODO: Implement rollback logic
        pass
```

---

### Running Seeders

**Run all seeders for a database:**
```bash
python cli.py seed --database postgres
```

**Run specific seeder:**
```bash
python cli.py seed --class DefaultDataSeeder --database postgres
```

---

## 🔌 Database Adapters

### PostgreSQL Adapter

**Features:**
- Full SQL support
- Transaction management
- Async/sync operations
- SQLAlchemy integration

**Methods:**
- `execute(query, params)` - Execute SQL
- `fetch_one(query, params)` - Fetch single row
- `fetch_all(query, params)` - Fetch all rows

---

### Redis Adapter

**Features:**
- Key-value operations
- Hash operations
- TTL support
- Sorted sets for version tracking

**Methods:**
- `set(key, value, ex)` - Set key with optional TTL
- `get(key)` - Get value
- `delete(*keys)` - Delete keys
- `hset(name, key, value)` - Set hash field
- `hget(name, key)` - Get hash field
- `expire(key, seconds)` - Set TTL

---

### InfluxDB Adapter

**Features:**
- Bucket management
- Flux query support
- Retention policies
- Time-series data

**Methods:**
- `create_bucket(name, retention_days)` - Create bucket
- `delete_bucket(name)` - Delete bucket
- `write_point(bucket, measurement, tags, fields)` - Write data
- `execute(query)` - Execute Flux query

---

### Elasticsearch Adapter

**Features:**
- Index management
- Mapping definitions
- Index templates
- Query DSL support

**Methods:**
- `create_index(name, mappings, settings)` - Create index
- `delete_index(name)` - Delete index
- `put_mapping(index, mappings)` - Update mappings
- `create_index_template(name, body)` - Create template
- `execute(query, params)` - Execute query

---

### Kafka Adapter

**Features:**
- Topic management
- Partition configuration
- Retention policies
- Compression settings

**Methods:**
- `create_topic(name, partitions, replication_factor, configs)` - Create topic
- `delete_topic(name)` - Delete topic
- `list_topics()` - List all topics
- `alter_topic_config(name, configs)` - Update configuration

---

## ✍️ Writing Migrations

### PostgreSQL Migration Example

```python
from infrastructure.migrations.core.base_migration import BaseMigration

class CreateUsersTable(BaseMigration):
    """Create users table with indexes"""
    
    def up(self, adapter):
        """Run migration"""
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE INDEX idx_users_email ON users(email)
        """)
        
        print("    ✓ Created users table")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS users CASCADE")
        print("    ✓ Dropped users table")
```

### Redis Migration Example

```python
from infrastructure.migrations.core.base_migration import BaseMigration

class SetupCacheConfig(BaseMigration):
    """Setup Redis cache configuration"""
    
    def up(self, adapter):
        """Run migration"""
        adapter.set('config:cache:ttl', '3600')
        adapter.set('config:cache:enabled', 'true')
        adapter.hset('stats:cache', 'hits', '0')
        adapter.hset('stats:cache', 'misses', '0')
        print("    ✓ Configured cache settings")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.delete('config:cache:ttl', 'config:cache:enabled')
        adapter.delete('stats:cache')
        print("    ✓ Removed cache configuration")
```

### InfluxDB Migration Example

```python
from infrastructure.migrations.core.base_migration import BaseMigration

class CreateMetricsBucket(BaseMigration):
    """Create metrics bucket"""
    
    def up(self, adapter):
        """Run migration"""
        adapter.create_bucket('app_metrics', retention_days=30)
        print("    ✓ Created app_metrics bucket")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.delete_bucket('app_metrics')
        print("    ✓ Deleted app_metrics bucket")
```

---

## 🌱 Writing Seeders

### PostgreSQL Seeder Example

```python
from infrastructure.migrations.core.base_seeder import BaseSeeder

class DefaultUsersSeeder(BaseSeeder):
    """Seed default users"""
    
    def run(self, adapter):
        """Run seeder"""
        users = [
            ('admin@example.com', 'admin', 'hash123'),
            ('user@example.com', 'user', 'hash456'),
        ]
        
        for email, username, password_hash in users:
            adapter.execute(
                """
                INSERT INTO users (email, username, password_hash)
                VALUES (:email, :username, :password_hash)
                ON CONFLICT (email) DO NOTHING
                """,
                {'email': email, 'username': username, 'password_hash': password_hash}
            )
        
        print(f"    ✓ Seeded {len(users)} users")
```

### Redis Seeder Example

```python
from infrastructure.migrations.core.base_seeder import BaseSeeder

class CacheWarmupSeeder(BaseSeeder):
    """Warm up cache"""
    
    def run(self, adapter):
        """Run seeder"""
        config = {
            'app:name': 'AI4I Platform',
            'app:version': '1.0.0',
        }
        
        for key, value in config.items():
            adapter.set(f'cache:{key}', value, ex=86400)
        
        print(f"    ✓ Warmed up {len(config)} cache keys")
```

---

## ⚙️ Configuration

### Environment Variables

Edit `infrastructure/migrations/.env`:

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=dhruva_user
POSTGRES_PASSWORD=dhruva_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# InfluxDB
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-token-here
INFLUXDB_ORG=ai4i

# Elasticsearch
ELASTICSEARCH_HOSTS=http://localhost:9200
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

---

## 📚 Examples

### Complete Workflow Example

```bash
# 1. Check current status
python cli.py migrate:status

# 2. Create new migration
python cli.py make:migration add_user_roles --database postgres

# 3. Edit the generated migration file
# Add your up() and down() logic

# 4. Run migration
python cli.py migrate --database postgres

# 5. Verify
python cli.py migrate:status --database postgres

# 6. If needed, rollback
python cli.py rollback --database postgres
```

### Multi-Database Migration

```bash
# Migrate all databases at once
python cli.py migrate

# Or one by one
python cli.py migrate --database postgres
python cli.py migrate --database redis
python cli.py migrate --database influxdb
python cli.py migrate --database elasticsearch
python cli.py migrate --database kafka
```

---

## 🎯 Best Practices

1. **Always test migrations** in development before production
2. **Write reversible migrations** - implement both `up()` and `down()`
3. **Use transactions** where supported (PostgreSQL)
4. **Version control** your migration files
5. **Keep migrations small** - one logical change per migration
6. **Name migrations clearly** - use descriptive names
7. **Test rollbacks** before deploying
8. **Document complex logic** in migration docstrings

---

## 🔍 Troubleshooting

### Connection Issues

If you get connection errors:
1. Check your `.env` file configuration
2. Verify database services are running
3. Test connections manually

### Migration Fails

If a migration fails:
1. Check the error message
2. Verify migration syntax
3. Check database permissions
4. Manually rollback if needed

### Version Tracking Issues

If migrations show incorrect status:
1. Check `migrations` table/structure in database
2. Verify adapter connection
3. Re-run `create_migrations_table()`

---

## 🤝 Contributing

To add support for a new database:

1. Create adapter in `adapters/`
2. Extend `BaseAdapter`
3. Implement all abstract methods
4. Add to `config.py`
5. Create sample migration
6. Update documentation

---

## 📄 License

Part of AI4I Core Platform - See main project LICENSE

---

## 🙏 Credits

Inspired by Laravel's Eloquent migrations and designed for the AI4I Core microservices platform.

---

**Made with ❤️ for AI4I Core**

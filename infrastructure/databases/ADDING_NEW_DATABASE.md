# Adding a New Database to the Migration System

This guide explains how to add a new database to the migration framework.

## 📋 Steps to Add a New PostgreSQL Database

### 1. Register the Database

Edit `infrastructure/databases/cli.py` and add your database to the `POSTGRES_DBS` list:

```python
POSTGRES_DBS = [
    'auth_db', 
    'config_db', 
    'alerting_db',
    'metrics_db',
    'telemetry_db',
    'dashboard_db',
    'model_management_db', 
    'multi_tenant_db',
    'dhruva_platform',
    'your_new_db',  # ← Add your database here
]
```

### 2. Add Database Configuration

Edit `infrastructure/databases/config.py` and add connection details:

```python
'your_new_db': {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': 'your_new_db',
    'user': os.getenv('POSTGRES_USER', 'dhruva_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'dhruva_password'),
}
```

### 3. Create Migration Files

```bash
# Create your first migration
python3 infrastructure/databases/cli.py make:migration create_initial_tables \
    --database postgres --postgres-db your_new_db
```

This creates: `infrastructure/databases/migrations/postgres/2024_02_15_XXXXXX_create_initial_tables.py`

### 4. Write Migration Code

Edit the generated file:

```python
from infrastructure.databases.core.base_migration import BaseMigration

class CreateInitialTables(BaseMigration):
    """Create initial tables for your_new_db"""
    
    database = 'your_new_db'
    
    def up(self):
        """Run migration"""
        self.execute("""
            CREATE TABLE your_table (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX idx_your_table_name ON your_table(name);
        """)
    
    def down(self):
        """Rollback migration"""
        self.execute("DROP TABLE IF EXISTS your_table CASCADE;")
```

### 5. Create Seeder (Optional)

Create `infrastructure/databases/seeders/postgres/your_new_db_seeder.py`:

```python
from infrastructure.databases.core.base_seeder import BaseSeeder

class YourNewDbSeeder(BaseSeeder):
    """Seed default data for your_new_db"""
    
    database = 'your_new_db'
    
    def run(self):
        """Run seeder"""
        self.execute("""
            INSERT INTO your_table (name) VALUES
            ('Default Item 1'),
            ('Default Item 2'),
            ('Default Item 3');
        """)
        
        print("✅ Seeded your_new_db with default data")
```

If you created a seeder, add it to the `seed_all` method in `cli.py`:

```python
postgres_dbs_with_seeders = [
    'auth_db', 'config_db', 'alerting_db', 
    'dashboard_db', 'multi_tenant_db', 'dhruva_platform',
    'your_new_db',  # ← Add here
]
```

### 6. Run Migrations

```bash
# Migrate ALL databases (including your new one)
python3 infrastructure/databases/cli.py migrate:all

# Or migrate just your database
python3 infrastructure/databases/cli.py migrate --database postgres --postgres-db your_new_db

# Run seeders
python3 infrastructure/databases/cli.py seed:all
```

### 7. Verify

```bash
# Check migration status
python3 infrastructure/databases/cli.py migrate:status --database postgres --postgres-db your_new_db

# Connect to database
docker exec -it ai4v-postgres psql -U dhruva_user -d your_new_db -c "\dt"
```

---

## 📋 Steps to Add a New Non-PostgreSQL Database

### 1. Register the Database Type

Edit `infrastructure/databases/cli.py`:

```python
DATABASES = ['postgres', 'redis', 'influxdb', 'elasticsearch', 'kafka', 'your_db_type']
```

### 2. Create Database Adapter

Create `infrastructure/databases/adapters/your_db_adapter.py`:

```python
from infrastructure.databases.core.base_adapter import BaseAdapter

class YourDbAdapter(BaseAdapter):
    """Adapter for Your Database"""
    
    def __init__(self, config):
        super().__init__(config)
        # Initialize your database connection
        self.client = YourDbClient(
            host=config['host'],
            port=config['port']
        )
    
    def execute(self, query):
        """Execute a query"""
        return self.client.execute(query)
    
    def close(self):
        """Close connection"""
        self.client.close()
```

### 3. Register Adapter

Edit `infrastructure/databases/config.py`:

```python
from infrastructure.databases.adapters.your_db_adapter import YourDbAdapter

@staticmethod
def get_adapter_class(database_type: str):
    adapters = {
        'postgres': PostgresAdapter,
        'redis': RedisAdapter,
        'influxdb': InfluxDBAdapter,
        'elasticsearch': ElasticsearchAdapter,
        'kafka': KafkaAdapter,
        'your_db_type': YourDbAdapter,  # ← Add here
    }
    return adapters.get(database_type)
```

### 4. Add Configuration

Edit `infrastructure/databases/config.py`:

```python
'your_db_type': {
    'host': os.getenv('YOUR_DB_HOST', 'localhost'),
    'port': int(os.getenv('YOUR_DB_PORT', 1234)),
}
```

### 5. Create Migrations

```bash
python3 infrastructure/databases/cli.py make:migration setup_your_db --database your_db_type
```

### 6. Run Migrations

```bash
# Migrate all (including your new database)
python3 infrastructure/databases/cli.py migrate:all

# Or just your database
python3 infrastructure/databases/cli.py migrate --database your_db_type
```

---

## ✅ Benefits of This Approach

1. **Auto-Discovery**: Just add to `POSTGRES_DBS` list, no need to update loops
2. **Single Command**: `migrate:all` automatically picks up new databases
3. **Consistent**: Same process for all databases
4. **Maintainable**: One place to register databases
5. **Scalable**: Easy to add 10, 20, or 100 databases

---

## 🎯 Example: Adding `analytics_db`

```bash
# 1. Add to cli.py POSTGRES_DBS list
# 2. Create migration
python3 infrastructure/databases/cli.py make:migration create_analytics_tables \
    --database postgres --postgres-db analytics_db

# 3. Edit migration file
# 4. Run migration
python3 infrastructure/databases/cli.py migrate:all

# Done! ✅
```

No need to update any loops or deployment scripts!

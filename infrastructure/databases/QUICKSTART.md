# 🚀 Quick Start Guide - Migration Framework

Get started with the AI4I Core Migration Framework in 5 minutes!

---

## Step 1: Install Dependencies

```bash
cd /Users/vipuldholariya/Documents/ai4i-core/infrastructure/databases
pip install -r requirements.txt
```

---

## Step 2: Configure Database Connections

The system will use your existing environment variables or Docker Compose settings. By default:

- **PostgreSQL**: `localhost:5432` (user: `dhruva_user`)
- **Redis**: `localhost:6379`
- **InfluxDB**: `http://localhost:8086`
- **Elasticsearch**: `http://localhost:9200`
- **Kafka**: `localhost:9092`

If using Docker Compose, your databases are already configured!

---

## Step 3: Check Current Status

```bash
cd /Users/vipuldholariya/Documents/ai4i-core
python infrastructure/databases/cli.py migrate:status
```

You'll see the migration status for all databases.

---

## Step 4: Run Sample Migrations

```bash
# Run all database migrations
python infrastructure/databases/cli.py migrate

# Or migrate individually
python infrastructure/databases/cli.py migrate --database postgres
python infrastructure/databases/cli.py migrate --database redis
python infrastructure/databases/cli.py migrate --database influxdb
python infrastructure/databases/cli.py migrate --database elasticsearch
python infrastructure/databases/cli.py migrate --database kafka
```

---

## Step 5: Run Seeders (Optional)

```bash
# Seed all databases with sample data
python infrastructure/databases/cli.py seed --database postgres
python infrastructure/databases/cli.py seed --database redis
python infrastructure/databases/cli.py seed --database influxdb
```

---

## Step 6: Create Your First Migration

```bash
# Create a new PostgreSQL migration
python infrastructure/databases/cli.py make:migration create_my_table --database postgres
```

This creates a file at:
```
infrastructure/databases/migrations/postgres/2024_02_15_HHMMSS_create_my_table.py
```

Edit the file and add your logic:

```python
from infrastructure.migrations.core.base_migration import BaseMigration

class CreateMyTable(BaseMigration):
    """Create my_table"""
    
    def up(self, adapter):
        """Run migration"""
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS my_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created my_table")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS my_table CASCADE")
        print("    ✓ Dropped my_table")
```

---

## Step 7: Run Your Migration

```bash
python infrastructure/databases/cli.py migrate --database postgres
```

---

## Step 8: Test Rollback

```bash
python infrastructure/databases/cli.py rollback --database postgres
```

---

## Common Commands Cheat Sheet

```bash
# Status
python infrastructure/databases/cli.py migrate:status

# Migrate all
python infrastructure/databases/cli.py migrate

# Migrate specific database
python infrastructure/databases/cli.py migrate --database postgres

# Rollback
python infrastructure/databases/cli.py rollback --database postgres

# Fresh (drop all & recreate)
python infrastructure/databases/cli.py migrate:fresh --database postgres

# Create migration
python infrastructure/databases/cli.py make:migration <name> --database <db>

# Run seeders
python infrastructure/databases/cli.py seed --database postgres

# Run specific seeder
python infrastructure/databases/cli.py seed --class MySeeder --database postgres
```

---

## For Docker Users

If your databases are in Docker Compose:

```bash
# Make sure containers are running
docker compose up -d postgres redis influxdb elasticsearch kafka

# Then run migrations
python infrastructure/databases/cli.py migrate
```

---

## For Production

1. **Test in development first**
2. **Backup your databases**
3. **Review migration files**
4. **Run migrations during maintenance window**
5. **Monitor for errors**
6. **Keep rollback ready**

```bash
# Production migration (example)
python infrastructure/databases/cli.py migrate --database postgres
```

---

## Need Help?

- 📖 Read the full [README.md](README.md)
- 🐛 Check troubleshooting section
- 📁 See example migrations in `migrations/` directory
- 🌱 See example seeders in `seeders/` directory

---

**That's it! You're ready to manage your multi-database migrations! 🎉**

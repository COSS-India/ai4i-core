# 🚀 Database Migration System - Deployment Guide

Complete guide to deploy and run the migration system.

---

## 📋 Prerequisites

- Python 3.9+
- Docker & Docker Compose
- PostgreSQL, Redis, InfluxDB, Elasticsearch, Kafka (via Docker)

---

## 🔧 Step 1: Install Python Dependencies

```bash
cd /Users/vipuldholariya/Documents/ai4i-core
pip3 install -r infrastructure/databases/requirements.txt
```

**Required packages:**
- `psycopg2-binary` - PostgreSQL adapter
- `redis` - Redis client
- `influxdb-client` - InfluxDB client
- `elasticsearch` - Elasticsearch client
- `kafka-python` - Kafka client

---

## 🐳 Step 2: Start Databases

### Start All Databases:
```bash
docker-compose -f docker-compose-simple.yml up -d
```

### Or Start Specific Databases:
```bash
# Essential databases
docker-compose -f docker-compose-simple.yml up -d postgres redis influxdb

# Check status
docker ps | grep -E "postgres|redis|influx"
```

---

## 🗄️ Step 3: Run Migrations

### **✨ NEW: Migrate ALL databases with ONE command:**

```bash
# Auto-migrates all 13 databases (no need to list them!)
python3 infrastructure/databases/cli.py migrate:all
```

**This automatically runs migrations for:**
- ✅ All 9 PostgreSQL databases
- ✅ Redis
- ✅ InfluxDB
- ✅ Elasticsearch
- ✅ Kafka

**Or migrate specific database if needed:**
```bash
python3 infrastructure/databases/cli.py migrate --database postgres --postgres-db auth_db
python3 infrastructure/databases/cli.py migrate --database redis
```

---

## 🌱 Step 4: Run Seeders

### **✨ NEW: Seed ALL databases with ONE command:**

```bash
# Auto-seeds all databases with default data (no need to list them!)
python3 infrastructure/databases/cli.py seed:all
```

**This automatically runs seeders for all databases that have them:**
- ✅ auth_db (Roles, Permissions, Admin User)
- ✅ config_db (Default Configurations)
- ✅ alerting_db (Default Alert Rules)
- ✅ dashboard_db (Default Dashboards)
- ✅ multi_tenant_db (Service Configurations)
- ✅ dhruva_platform (Policy Engine Defaults)
- ✅ Redis (Cache Configuration)
- ✅ InfluxDB (Sample Metrics)

**Or seed specific database if needed:**
```bash
python3 infrastructure/databases/cli.py seed --database postgres --postgres-db auth_db
python3 infrastructure/databases/cli.py seed --database redis
```

**Default Admin Credentials:**
- Email: `admin@ai4inclusion.org`
- Username: `admin`
- Password: `Admin@123`

---

## ✅ Step 5: Verify Deployment

### Check Migration Status:
```bash
python3 infrastructure/databases/cli.py migrate:status --database postgres --postgres-db auth_db
```

### Verify Tables in Database:
```bash
# Connect to PostgreSQL
docker exec -it ai4v-postgres psql -U dhruva_user -d auth_db

# List all tables
\dt

# Check users table
SELECT id, username, email FROM users;

# Exit
\q
```

### Test API Connectivity:
```bash
# If your API is running, test with default admin
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'
```

---

## 🔄 Step 6: Future Migrations

### Create New Migration:
```bash
python3 infrastructure/databases/cli.py make:migration add_new_column --database postgres
```

### Run Specific Migration:
```bash
python3 infrastructure/databases/cli.py migrate --database postgres --postgres-db auth_db --steps 1
```

### Rollback Migration:
```bash
python3 infrastructure/databases/cli.py rollback --database postgres --postgres-db auth_db --steps 1
```

### Fresh Install (Reset Everything):
```bash
python3 infrastructure/databases/cli.py migrate:fresh --database postgres --postgres-db auth_db
```

---

## 📊 Database Coverage

| Database | Tables | Migrations | Seeders | Status |
|----------|--------|-----------|---------|--------|
| auth_db | 31 | 9 | 2 | ✅ |
| config_db | 5 | 2 | 1 | ✅ |
| alerting_db | 10 | 8 | 1 | ✅ |
| metrics_db | 4 | 3 | 0 | ✅ |
| telemetry_db | 4 | 3 | 0 | ✅ |
| dashboard_db | 5 | 3 | 1 | ✅ |
| model_management_db | 5 | 7 | 0 | ✅ |
| multi_tenant_db | 7 | 5 | 1 | ✅ |
| dhruva_platform | 1 | 1 | 1 | ✅ |
| Redis | - | 1 | 1 | ✅ |
| InfluxDB | - | 1 | 1 | ✅ |
| Elasticsearch | - | 1 | 0 | ✅ |
| Kafka | - | 1 | 0 | ✅ |

**Total: 13 databases, 45 migrations, 9 seeders**

---

## 🚀 Quick Start Script (One Command)

### **Option 1: Use the deployment script (Recommended)**

```bash
cd /Users/vipuldholariya/Documents/ai4i-core
./infrastructure/databases/deploy-migrations.sh
```

### **Option 2: Manual one-liner**

```bash
# Install, start, migrate, and seed everything
pip3 install -r infrastructure/databases/requirements.txt && \
docker-compose -f docker-compose-simple.yml up -d && \
sleep 10 && \
python3 infrastructure/databases/cli.py migrate:all && \
python3 infrastructure/databases/cli.py seed:all
```

**That's it!** ✨ The system auto-discovers all databases from the configuration.

---

## 🔍 Troubleshooting

### Issue: "No module named 'redis'"
**Solution:** Install dependencies
```bash
pip3 install -r infrastructure/databases/requirements.txt
```

### Issue: "Connection refused"
**Solution:** Start databases
```bash
docker-compose -f docker-compose-simple.yml up -d
docker ps  # verify running
```

### Issue: "Database does not exist"
**Solution:** Create databases first (they should be created automatically by init scripts)
```bash
docker exec -it ai4v-postgres psql -U dhruva_user -c "CREATE DATABASE auth_db;"
```

### Issue: Migration fails halfway
**Solution:** Check status and rollback if needed
```bash
python3 infrastructure/databases/cli.py migrate:status --database postgres --postgres-db auth_db
python3 infrastructure/databases/cli.py rollback --database postgres --postgres-db auth_db
```

---

## 📚 Additional Commands

### List all available commands:
```bash
python3 infrastructure/databases/cli.py --help
```

### Create custom seeder:
```bash
python3 infrastructure/databases/cli.py make:seeder CustomDataSeeder --database postgres
```

### Run specific seeder:
```bash
python3 infrastructure/databases/cli.py seed --database postgres --postgres-db auth_db --class AuthRolesPermissionsSeeder
```

---

## ✅ Success Criteria

You'll know everything is working when:

- ✅ All migrations run without errors
- ✅ 72+ tables created across 9 PostgreSQL databases
- ✅ Default admin user exists: `admin@ai4inclusion.org`
- ✅ 40+ permissions are loaded
- ✅ 4 default roles created (ADMIN, USER, GUEST, MODERATOR)
- ✅ Redis cache is configured
- ✅ InfluxDB has metrics bucket
- ✅ Elasticsearch has logs index
- ✅ Kafka has event topics

---

## 🎯 Next Steps After Deployment

1. **Test the Admin Login** with credentials above
2. **Connect your application** to the databases
3. **Create new migrations** as your schema evolves
4. **Set up CI/CD** to run migrations automatically
5. **Monitor migration status** in production

---

**Status:** ✅ Ready for Production Deployment

For more details, see:
- `README.md` - Full documentation
- `QUICKSTART.md` - Quick reference
- `DEPLOYMENT_CHECKLIST.md` - Pre-flight checklist

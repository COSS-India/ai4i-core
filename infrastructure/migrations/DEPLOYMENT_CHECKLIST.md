# 🚀 Production Deployment Checklist

## Pre-Deployment Verification

### ✅ Step 1: Verify Database Connections

```bash
# Test PostgreSQL connection
docker compose exec postgres psql -U dhruva_user -d auth_db -c "SELECT 1"

# Test Redis connection  
docker compose exec redis redis-cli ping

# Test InfluxDB connection
curl http://localhost:8086/health

# Test Elasticsearch connection
curl http://localhost:9200/_cluster/health

# Test Kafka connection
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

### ✅ Step 2: Install Dependencies

```bash
cd /Users/vipuldholariya/Documents/ai4i-core/infrastructure/migrations
pip install -r requirements.txt
```

### ✅ Step 3: Check Current Status

```bash
cd /Users/vipuldholariya/Documents/ai4i-core
python infrastructure/migrations/cli.py migrate:status
```

---

## Production Deployment Steps

### 🗄️ PostgreSQL Migrations

#### Auth Database (auth_db)

```bash
# Run migrations
python infrastructure/migrations/cli.py migrate --database postgres --postgres-db auth_db

# Run seeders (creates admin user, roles, permissions)
python infrastructure/migrations/cli.py seed --database postgres --postgres-db auth_db

# Verify
python infrastructure/migrations/cli.py migrate:status --database postgres --postgres-db auth_db
```

**Tables Created:**
- ✅ users (with indexes)
- ✅ roles (ADMIN, USER, GUEST, MODERATOR)
- ✅ permissions (40+ permissions)
- ✅ user_roles (many-to-many)
- ✅ role_permissions (many-to-many)
- ✅ api_keys
- ✅ sessions
- ✅ oauth_providers
- ✅ **11 AI Service tables** (ASR, TTS, NMT, LLM, OCR, NER, etc.)

**Default Admin Created:**
- Email: `admin@ai4i.org`
- Password: `Admin@123`
- Role: ADMIN

#### Config Database (config_db)

```bash
# Run migrations
python infrastructure/migrations/cli.py migrate --database postgres --postgres-db config_db

# Run seeders (creates default configs, feature flags, service registry)
python infrastructure/migrations/cli.py seed --database postgres --postgres-db config_db

# Verify
python infrastructure/migrations/cli.py migrate:status --database postgres --postgres-db config_db
```

**Tables Created:**
- ✅ configurations (service configs)
- ✅ feature_flags (with rollout %)
- ✅ service_registry (13 services)
- ✅ configuration_history (audit trail)
- ✅ feature_flag_evaluations (tracking)

### 💾 Redis Configuration

```bash
# Run migration (cache, sessions, rate limits)
python infrastructure/migrations/cli.py migrate --database redis

# Run seeder (warmup cache)
python infrastructure/migrations/cli.py seed --database redis

# Verify
python infrastructure/migrations/cli.py migrate:status --database redis
```

**Configured:**
- ✅ Cache settings (TTL, prefixes)
- ✅ Session management (2h sessions, 7d refresh)
- ✅ Rate limits per service (1000-5000 req/min)
- ✅ Statistics counters
- ✅ Feature flag sync (5min interval)

### 📊 InfluxDB Buckets

```bash
# Run migration (creates 6 buckets)
python infrastructure/migrations/cli.py migrate --database influxdb

# Run seeder (optional sample data)
python infrastructure/migrations/cli.py seed --database influxdb

# Verify
python infrastructure/migrations/cli.py migrate:status --database influxdb
```

**Buckets Created:**
- ✅ ai_service_metrics (30 days)
- ✅ system_performance (7 days)
- ✅ api_gateway_metrics (30 days)
- ✅ business_metrics (90 days)
- ✅ model_performance (90 days)
- ✅ metrics_archive (365 days)

### 🔍 Elasticsearch Indices

```bash
# Run migration (logs indices and templates)
python infrastructure/migrations/cli.py migrate --database elasticsearch

# Verify
python infrastructure/migrations/cli.py migrate:status --database elasticsearch
```

**Indices Created:**
- ✅ application-logs (structured logs)
- ✅ error-logs (error tracking)
- ✅ logs-template (time-series template)

### 📨 Kafka Topics

```bash
# Run migration (event topics)
python infrastructure/migrations/cli.py migrate --database kafka

# Verify
python infrastructure/migrations/cli.py migrate:status --database kafka
```

**Topics Created:**
- ✅ ai-events (6 partitions, 7d retention)
- ✅ user-activity (3 partitions, 30d retention)
- ✅ system-metrics (4 partitions, 3d retention)
- ✅ audit-logs (2 partitions, 90d retention)

---

## Post-Deployment Verification

### 1. Verify Admin Login

```bash
# Test admin user exists
docker compose exec postgres psql -U dhruva_user -d auth_db -c "SELECT * FROM users WHERE email = 'admin@ai4i.org'"

# Test admin has ADMIN role
docker compose exec postgres psql -U dhruva_user -d auth_db -c "
SELECT u.email, r.name 
FROM users u 
JOIN user_roles ur ON u.id = ur.user_id 
JOIN roles r ON ur.role_id = r.id 
WHERE u.email = 'admin@ai4i.org'
"
```

### 2. Verify Permissions

```bash
# Check total permissions created
docker compose exec postgres psql -U dhruva_user -d auth_db -c "SELECT COUNT(*) FROM permissions"

# Expected: 40+ permissions
```

### 3. Verify Service Registry

```bash
# Check service registry entries
docker compose exec postgres psql -U dhruva_user -d config_db -c "SELECT service_name, status FROM service_registry"

# Expected: 13 services
```

### 4. Verify Redis Configuration

```bash
# Check cache config
docker compose exec redis redis-cli GET ai4i:config:cache:default_ttl

# Check rate limit config
docker compose exec redis redis-cli GET "ai4i:config:ratelimit:asr-service:max_requests"
```

### 5. Verify InfluxDB Buckets

```bash
# List all buckets
curl -X GET "http://localhost:8086/api/v2/buckets" \
  -H "Authorization: Token YOUR_TOKEN"

# Expected: 6 buckets
```

### 6. Verify Elasticsearch Indices

```bash
# List indices
curl http://localhost:9200/_cat/indices?v

# Expected: application-logs, error-logs
```

### 7. Verify Kafka Topics

```bash
# List topics
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Expected: ai-events, user-activity, system-metrics, audit-logs
```

---

## Rollback Procedure

If something goes wrong:

```bash
# Rollback PostgreSQL (auth_db)
python infrastructure/migrations/cli.py rollback --database postgres --postgres-db auth_db

# Rollback PostgreSQL (config_db)
python infrastructure/migrations/cli.py rollback --database postgres --postgres-db config_db

# Rollback Redis
python infrastructure/migrations/cli.py rollback --database redis

# Rollback InfluxDB
python infrastructure/migrations/cli.py rollback --database influxdb

# Rollback Elasticsearch
python infrastructure/migrations/cli.py rollback --database elasticsearch

# Rollback Kafka
python infrastructure/migrations/cli.py rollback --database kafka
```

---

## Fresh Install (Development Only)

⚠️ **WARNING: This will DELETE ALL DATA!**

```bash
# Fresh install with seed data
python infrastructure/migrations/cli.py migrate:fresh --seed --database postgres --postgres-db auth_db
python infrastructure/migrations/cli.py migrate:fresh --seed --database postgres --postgres-db config_db
python infrastructure/migrations/cli.py migrate:fresh --database redis
python infrastructure/migrations/cli.py migrate:fresh --database influxdb
python infrastructure/migrations/cli.py migrate:fresh --database elasticsearch
python infrastructure/migrations/cli.py migrate:fresh --database kafka
```

---

## Production Checklist

- [ ] All database services running
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Environment variables configured
- [ ] Database connections verified
- [ ] Migrations run successfully
- [ ] Seeders run successfully
- [ ] Admin user login tested
- [ ] Permissions verified
- [ ] Service registry populated
- [ ] Redis cache configured
- [ ] InfluxDB buckets created
- [ ] Elasticsearch indices created
- [ ] Kafka topics created
- [ ] All verification tests passed
- [ ] Team notified of new system
- [ ] Old SQL files marked as deprecated
- [ ] Documentation updated

---

## Monitoring After Deployment

```bash
# Check migration status periodically
python infrastructure/migrations/cli.py migrate:status

# Monitor logs
tail -f logs/migrations.log  # if logging enabled

# Check database sizes
docker compose exec postgres psql -U dhruva_user -d auth_db -c "\l+"
```

---

## Support

- 📖 See `README.md` for full documentation
- 🚀 See `QUICKSTART.md` for quick reference
- 📋 See `PRODUCTION_MIGRATIONS_SUMMARY.md` for detailed implementation
- 🐛 Check troubleshooting section in README.md

---

**Deployment Date**: _______________  
**Deployed By**: _______________  
**Environment**: ☐ Development  ☐ Staging  ☐ Production  
**Status**: ☐ Success  ☐ Partial  ☐ Rollback Required

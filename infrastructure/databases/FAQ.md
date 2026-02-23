# Migration System FAQ

## 🔄 Running Migrations Multiple Times

### Q: Is it safe to run `migrate:all` multiple times?

**✅ YES - 100% SAFE!**

The migration system is **idempotent**, meaning you can run it multiple times without any issues.

### How It Works:

1. **Version Tracking Table**
   - A `migrations` table tracks all executed migrations
   - Stores: `migration_name`, `batch_number`, `executed_at`

2. **Automatic Skip Logic**
   ```python
   # Line 48 in migration_manager.py
   pending = self._get_pending_migrations()
   
   if not pending:
       print("✅ No pending migrations")
       return  # Safe exit - no changes made
   ```

3. **What Happens on Each Run:**

   **First Run:**
   ```bash
   $ python3 infrastructure/databases/cli.py migrate:all
   
   🗄️  Migrating auth_db...
     ⏳ Running: 2024_02_15_000001_create_auth_core_tables.py
     ✅ Migrated: 2024_02_15_000001_create_auth_core_tables.py
     ⏳ Running: 2024_02_15_000002_create_api_keys_sessions_tables.py
     ✅ Migrated: 2024_02_15_000002_create_api_keys_sessions_tables.py
     ... (all 45 migrations run)
   
   ✅ All databases migrated successfully!
   ```

   **Second Run (same command):**
   ```bash
   $ python3 infrastructure/databases/cli.py migrate:all
   
   🗄️  Migrating auth_db...
   ✅ No pending migrations for auth_db
   
   🗄️  Migrating config_db...
   ✅ No pending migrations for config_db
   
   ... (all databases checked, nothing runs)
   
   ✅ All databases migrated successfully!
   ```

   **Third Run (after adding NEW migration):**
   ```bash
   $ python3 infrastructure/databases/cli.py migrate:all
   
   🗄️  Migrating auth_db...
   ✅ No pending migrations for auth_db
   
   🗄️  Migrating config_db...
     ⏳ Running: 2024_02_15_100003_add_new_column.py
     ✅ Migrated: 2024_02_15_100003_add_new_column.py
   
   ✅ All databases migrated successfully!
   ```

### Key Benefits:

✅ **No Duplicate Execution** - Already-run migrations are skipped  
✅ **No Data Duplication** - Tables/indexes won't be created twice  
✅ **No Errors** - Safe to run in CI/CD pipelines  
✅ **Incremental Updates** - Only new migrations execute  
✅ **Rollback Support** - Batch tracking allows precise rollbacks  

---

## 🌱 Running Seeders Multiple Times

### Q: Is it safe to run `seed:all` multiple times?

**⚠️ DEPENDS ON YOUR SEEDER IMPLEMENTATION**

Unlike migrations, seeders do **NOT** have automatic duplicate prevention.

### What Happens:

**First Run:**
```bash
$ python3 infrastructure/databases/cli.py seed:all

🌱 Seeding auth_db...
  ✅ Inserted 3 roles (ADMIN, MODERATOR, USER)
  ✅ Inserted 50 permissions
  ✅ Created admin user
```

**Second Run:**
```bash
$ python3 infrastructure/databases/cli.py seed:all

🌱 Seeding auth_db...
  ❌ ERROR: duplicate key value violates unique constraint
```

### Solutions:

#### Option 1: Use `INSERT ... ON CONFLICT DO NOTHING` (Recommended)

```python
def run(self):
    self.execute("""
        INSERT INTO roles (name, description) VALUES
        ('ADMIN', 'Administrator'),
        ('MODERATOR', 'Moderator'),
        ('USER', 'Regular User')
        ON CONFLICT (name) DO NOTHING;
    """)
```

#### Option 2: Check Before Insert

```python
def run(self):
    # Check if already seeded
    result = self.execute("SELECT COUNT(*) FROM roles;")
    if result[0][0] > 0:
        print("⚠️  Roles already seeded, skipping...")
        return
    
    # Insert data
    self.execute("""
        INSERT INTO roles (name, description) VALUES
        ('ADMIN', 'Administrator'),
        ('MODERATOR', 'Moderator'),
        ('USER', 'Regular User');
    """)
```

#### Option 3: Use UPSERT

```python
def run(self):
    self.execute("""
        INSERT INTO roles (name, description) VALUES
        ('ADMIN', 'Administrator'),
        ('MODERATOR', 'Moderator'),
        ('USER', 'Regular User')
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description;
    """)
```

### Current Seeder Status:

Our seeders use **Option 1** (`ON CONFLICT DO NOTHING`), so they are **safe to run multiple times**.

---

## 🔄 Rollback Safety

### Q: Can I rollback after running migrations multiple times?

**✅ YES - Rollback is batch-aware**

```bash
# Run migrations (Batch 1)
$ python3 infrastructure/databases/cli.py migrate:all

# Add new migration and run again (Batch 2)
$ python3 infrastructure/databases/cli.py migrate:all

# Rollback only Batch 2
$ python3 infrastructure/databases/cli.py rollback --database postgres --postgres-db auth_db --steps 1
```

---

## 🚀 CI/CD Pipeline Usage

### Q: Can I use this in automated deployments?

**✅ YES - Perfect for CI/CD!**

```yaml
# Example: GitHub Actions
- name: Run Database Migrations
  run: |
    python3 infrastructure/databases/cli.py migrate:all
    python3 infrastructure/databases/cli.py seed:all
```

**Why it works:**
- ✅ Idempotent migrations
- ✅ Safe seeders (with `ON CONFLICT`)
- ✅ No manual intervention needed
- ✅ Automatic skip of already-run migrations

---

## 📊 Checking Migration Status

### Q: How do I see what's been run?

```bash
# Check all databases
$ python3 infrastructure/databases/cli.py migrate:status

# Check specific database
$ python3 infrastructure/databases/cli.py migrate:status --database postgres --postgres-db auth_db

Output:
📊 AUTH_DB Migration Status:
================================================================================
  ✅ Executed - 2024_02_15_000001_create_auth_core_tables.py
  ✅ Executed - 2024_02_15_000002_create_api_keys_sessions_tables.py
  ⏳ Pending - 2024_02_15_000010_add_new_feature.py
================================================================================
```

---

## 🔧 Troubleshooting

### Q: What if a migration fails halfway?

**The system is transactional:**

1. **PostgreSQL** - Uses transactions, automatic rollback on failure
2. **Other DBs** - Depends on database support

**Recovery:**
```bash
# Fix the migration file
# Then run again - it will skip successful ones and retry failed
$ python3 infrastructure/databases/cli.py migrate:all
```

### Q: How do I reset everything?

```bash
# Option 1: Fresh migration (drops all and re-runs)
$ python3 infrastructure/databases/cli.py migrate:fresh --database postgres --postgres-db auth_db

# Option 2: Manual rollback all
$ python3 infrastructure/databases/cli.py rollback --database postgres --postgres-db auth_db --steps 999

# Option 3: Drop database and re-create
$ docker-compose -f docker-compose-simple.yml down -v
$ docker-compose -f docker-compose-simple.yml up -d
$ python3 infrastructure/databases/cli.py migrate:all
```

---

## 🎯 Best Practices

### ✅ DO:
- Run `migrate:all` as many times as needed
- Use in CI/CD pipelines
- Check status before manual operations
- Use `ON CONFLICT` in seeders
- Test migrations in dev environment first

### ❌ DON'T:
- Modify already-executed migration files
- Delete migration files that have been run
- Run `migrate:fresh` in production
- Assume seeders are idempotent without checking

---

## 📈 Performance

### Q: Does running multiple times slow down deployment?

**No - it's very fast!**

- First run: ~10-30 seconds (runs all migrations)
- Subsequent runs: ~1-2 seconds (just checks tracking table)

The system only queries the `migrations` table to check status, making repeat runs extremely fast.

---

## 🔐 Production Safety

### Q: Is this production-ready?

**✅ YES - with these safeguards:**

1. **Backup First**
   ```bash
   # Backup before migrations
   docker exec ai4v-postgres pg_dump -U dhruva_user auth_db > backup.sql
   ```

2. **Test in Staging**
   ```bash
   # Run in staging first
   python3 infrastructure/databases/cli.py migrate:all
   ```

3. **Monitor Status**
   ```bash
   # Check what will run
   python3 infrastructure/databases/cli.py migrate:status
   ```

4. **Rollback Plan**
   ```bash
   # Know how to rollback
   python3 infrastructure/databases/cli.py rollback --steps 1
   ```

---

## Summary

| Action | Safe to Repeat? | Notes |
|--------|----------------|-------|
| `migrate:all` | ✅ YES | Skips already-run migrations |
| `seed:all` | ✅ YES | Our seeders use `ON CONFLICT` |
| `rollback` | ⚠️ CAREFUL | Only in dev/staging |
| `migrate:fresh` | ❌ NO | Drops all data! |

**Bottom Line:** Run `migrate:all` as many times as you want - it's designed for it! 🎉

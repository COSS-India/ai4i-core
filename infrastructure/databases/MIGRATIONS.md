# Database Migrations Guide

This project uses **Alembic** for database migrations with a thin CLI wrapper for convenience.

---

## Overview

- **Tool:** Alembic (standard Python database migration framework)
- **Location:** `infrastructure/databases/migrations/postgres/alembic/`
- **Per-database:** Each PostgreSQL database has its own migration folder
- **CLI:** Thin wrapper (`infrastructure/databases/cli.py`) around Alembic commands
- **Format:** Standard Alembic (upgrade/downgrade functions)
- **Version Tracking:** Alembic's native `alembic_version` table (no custom tracking)

---

## Where Migrations Live

```
infrastructure/databases/migrations/postgres/alembic/versions/
├── ai4iplatform_auth/          ← Auth-service database
├── ai4iplatform_core/
├── alerting_db/
├── policy_db/
└── ai4i_platform/
```

Each database folder contains numbered migration files:
```
ai4iplatform_auth/
├── a55cc68a99ce_auto_20260428_212435.py
├── b66dd69a00df_set_is_active_default_false.py
├── 2362774ac241_seed_default_data.py
└── ...
```

---

## Creating a New Migration

### 1. Generate Migration File

For **auth-service** (default database):
```bash
python infrastructure/databases/cli.py make:migration add_email_verified_column --postgres-db ai4iplatform_auth
```

For **other databases**:
```bash
python infrastructure/databases/cli.py make:migration create_audit_table --postgres-db alerting_db
```

### 2. Edit the Generated File

The CLI creates a template with placeholder functions. You fill in the logic:

```python
"""add_email_verified_column

Revision ID: a55cc68a99ce
Revises: 2362774ac241
Create Date: 2026-05-20 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a55cc68a99ce'
down_revision: Union[str, None] = '2362774ac241'  # ← Previous migration ID
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration — do not modify revision IDs."""
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Revert migration — must undo what upgrade() did."""
    op.drop_column('users', 'email_verified')
```

---

## Migration File Anatomy

| Field | Purpose | Do NOT Change |
|-------|---------|---------------|
| `revision` | Unique identifier for this migration | ✅ Auto-generated |
| `down_revision` | Previous migration's revision ID — chain migrations | ⚠️ Verify it's correct |
| `upgrade()` | Code to apply the change | ❌ Write this |
| `downgrade()` | Code to revert the change | ❌ Write this |

**Critical:** `down_revision` must point to the previous migration in the chain. If you get it wrong, the migration fails.

---

## Common Operations

### Add Column
```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'phone')
```

### Create Table
```python
def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )

def downgrade() -> None:
    op.drop_table('audit_logs')
```

### Add Index
```python
def upgrade() -> None:
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
```

### Add Foreign Key
```python
def upgrade() -> None:
    op.add_column('orders', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_foreign_key('fk_orders_user_id', 'orders', 'users', ['user_id'], ['id'])

def downgrade() -> None:
    op.drop_constraint('fk_orders_user_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'user_id')
```

### Add Enum
```python
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Create enum type
    status_enum = postgresql.ENUM('ACTIVE', 'INACTIVE', 'PENDING', name='user_status')
    status_enum.create(op.get_bind(), checkfirst=True)

    # Add column using enum
    op.add_column('users', sa.Column('status', status_enum, nullable=False, server_default='PENDING'))

def downgrade() -> None:
    op.drop_column('users', 'status')
    op.execute('DROP TYPE user_status')
```

### Alter Column (e.g., add NOT NULL)
```python
def upgrade() -> None:
    op.alter_column('users', 'email',
               existing_type=sa.String(),
               nullable=False,
               existing_nullable=True)

def downgrade() -> None:
    op.alter_column('users', 'email',
               existing_type=sa.String(),
               nullable=True,
               existing_nullable=False)
```

---

## Running Migrations

### Run All Pending Migrations

For auth-service (default):
```bash
python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth
```

For specific database:
```bash
python infrastructure/databases/cli.py migrate --postgres-db alerting_db
```

### Run Specific Number of Migrations
```bash
python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_core --steps 3
```

### Check Migration Status
```bash
python infrastructure/databases/cli.py migrate:status --postgres-db ai4iplatform_auth
```

Shows all applied migrations and their details:
```
Current revision(s) for postgresql+psycopg2://...
Rev: d3e850228f7e (head)
Parent: 908da7983d98
  seed_default_data

Rev: 908da7983d98
Parent: b8a6e529935f
  auto_20260427_113132
...
```

### Rollback Last Migration
```bash
python infrastructure/databases/cli.py rollback --postgres-db ai4iplatform_auth
```

### Rollback Multiple Migrations
```bash
python infrastructure/databases/cli.py rollback --postgres-db ai4iplatform_auth --steps 2
```

### Fresh Migration (Drop All + Re-run)
```bash
python infrastructure/databases/cli.py migrate:fresh --postgres-db ai4iplatform_auth --force
```

### Migrate All Databases at Once
```bash
python infrastructure/databases/cli.py migrate:all
```

---

## Important Rules

| Rule | Why | What Happens if Broken |
|------|-----|------------------------|
| ✅ Write both `upgrade()` AND `downgrade()` | Reversibility | Rollbacks fail; stuck state |
| ✅ Never edit `revision` ID after creation | Migration identity | Alembic loses track |
| ✅ Chain `down_revision` correctly | Dependency chain | Migrations skip or fail |
| ✅ Test rollback locally before push | Early detection | Production issues |
| ✅ Use `server_default` for backfill | Data safety | Inconsistent state |
| ❌ Never use `DROP TABLE` without backup context | Data loss | Unrecoverable |

---

## Workflow

1. **Create** migration file
   ```bash
   python infrastructure/databases/cli.py make:migration add_user_roles --postgres-db ai4iplatform_auth
   ```

2. **Edit** the generated file with upgrade/downgrade logic

3. **Test upgrade** — run migrations locally
   ```bash
   python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth
   ```

4. **Test downgrade** — rollback and verify
   ```bash
   python infrastructure/databases/cli.py rollback --postgres-db ai4iplatform_auth
   ```

5. **Verify status**
   ```bash
   python infrastructure/databases/cli.py migrate:status --postgres-db ai4iplatform_auth
   ```

6. **Re-apply** for final test
   ```bash
   python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth
   ```

7. **Commit** the migration file to git

8. **Merge** to main

9. **Deploy** — run migrations in target environment
   ```bash
   python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth
   ```

---

## Troubleshooting

### Migration fails to run
- Check `down_revision` points to actual previous migration
- Verify SQL syntax (test in psql directly)
- Check constraints aren't violated (FK, NOT NULL, etc.)

### "Duplicate revision ID"
- Don't reuse revision IDs
- Delete and regenerate if needed

### "Connection refused" to database
- Ensure PostgreSQL is running on correct host/port
- Check `.env` in `infrastructure/databases/migrations/postgres/alembic/` overrides

### "No operations to run"
- New migrations already applied
- Check migration status: `python infrastructure/databases/cli.py migrate:status`

---

## Local Development

For local dev with Docker containers:

```bash
# Start postgres + redis
docker-compose -f docker-compose-local.yml up postgres redis -d

# Create and test migration
python infrastructure/databases/cli.py make:migration my_change --postgres-db ai4iplatform_auth
# Edit the file...

# Run migration
python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth

# Test rollback
python infrastructure/databases/cli.py rollback --postgres-db ai4iplatform_auth

# Verify it's rolled back
python infrastructure/databases/cli.py migrate:status --postgres-db ai4iplatform_auth

# Re-apply for final test
python infrastructure/databases/cli.py migrate --postgres-db ai4iplatform_auth
```

---

---

## Preventing Common Mistakes

### 1. Use the CLI (Never Create Files Manually)

❌ **Wrong:**
```bash
# Don't create files manually
touch infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_auth/xyz_my_migration.py
```

✅ **Right:**
```bash
# Always use CLI — it auto-generates revision IDs and sets down_revision
python infrastructure/databases/cli.py make:migration my_change --database postgres
```

**Why:** Manual files break the revision chain and don't get proper IDs.

---

### 2. Verify Your Migration Chain Before Committing

Run the validator:
```bash
python scripts/validate-migrations.py
```

**Check for:**
```
✓ PASS  ai4iplatform_auth: chain intact (5 revisions)
✗ FAIL  ai4iplatform_auth: multiple heads detected (2): ['abc123', 'def456']
```

If you see "multiple heads," it means two migrations claim to be the latest. Fix with:
```bash
alembic -x db=ai4iplatform_auth merge heads -m 'merge branches'
```

---

### 3. Never Edit `revision` or `down_revision` After Creation

❌ **Wrong:**
```python
# Don't change these after creation!
revision: str = 'xyz789'  # ← Don't edit
down_revision: Union[str, None] = 'abc123'  # ← Don't edit
```

✅ **Right:**
```python
# Leave them as auto-generated
# Only edit: upgrade() and downgrade()
```

**Why:** Alembic uses revision IDs to track applied migrations. Editing them breaks the history.

---

### 4. Always Write Downgrade Logic

❌ **Wrong:**
```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20)))

def downgrade() -> None:
    pass  # ← Empty! Can't rollback
```

✅ **Right:**
```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20)))

def downgrade() -> None:
    op.drop_column('users', 'phone')  # ← Mirrors upgrade
```

**Why:** You WILL need to rollback at some point. Test it locally first.

---

### 5. Test Rollback Before Pushing

```bash
# After creating migration, test it works
python infrastructure/databases/cli.py migrate
python infrastructure/databases/cli.py migrate:status  # ← See it applied

# Then test rollback
python infrastructure/databases/cli.py rollback
python infrastructure/databases/cli.py migrate:status  # ← Should show as pending

# Re-apply for final test
python infrastructure/databases/cli.py migrate
```

**If rollback fails**, you'll catch the bug locally instead of in production.

---

### 6. Put Migrations in the Right Database Folder

❌ **Wrong:**
```
infrastructure/databases/migrations/postgres/alembic/versions/
├── my_migration.py  ← Wrong place!
```

✅ **Right:**
```
infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_auth/
├── a55cc68a99ce_my_migration.py  ← Correct database folder
```

**Prevention:** Use the CLI with `--postgres-db` flag. It puts files in the right folder automatically.

---

### 7. Don't Break the down_revision Chain

❌ **Wrong:**
```python
# Migration created today:
revision: str = 'xyz789'
down_revision: Union[str, None] = 'nonexistent_id'  # ← This ID doesn't exist!
```

✅ **Right:**
```python
# CLI auto-sets down_revision to the previous migration
revision: str = 'xyz789'
down_revision: Union[str, None] = 'c4e8f1a2b3d0'  # ← This migration exists
```

**Prevention:** Never manually edit `down_revision`. The CLI sets it correctly.

---

### 8. Pre-Commit Validation (Git Hooks)

Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
echo "Validating migrations..."
python scripts/validate-migrations.py
if [ $? -ne 0 ]; then
    echo "❌ Migration validation failed. Fix and try again."
    exit 1
fi
echo "✓ Migrations valid"
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

Now migrations are validated before every commit.

---

### 9. Code Review Checklist

When reviewing a PR with migrations:

- ✅ Used CLI to create (`make:migration`)
- ✅ `down_revision` points to previous migration
- ✅ Both `upgrade()` and `downgrade()` are complete
- ✅ Downgrade mirrors upgrade (add/drop, create/drop, etc.)
- ✅ Runs `scripts/validate-migrations.py` cleanly
- ✅ Developer tested locally with rollback
- ✅ No manual edits to revision IDs

---

### 10. CI/CD Integration

Add to your GitHub Actions / GitLab CI:

```yaml
# .github/workflows/migrations.yml
name: Validate Migrations
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: python scripts/validate-migrations.py
```

Migrations are validated automatically on every PR.

---

## Summary: The Right Way

| Step | Command | Why |
|------|---------|-----|
| 1. Create | `python cli.py make:migration add_x_column --postgres-db <db>` | Alembic generates correct IDs + location |
| 2. Edit | Add logic to `upgrade()` and `downgrade()` | Make reversible |
| 3. Verify Chain | `python scripts/validate-migrations.py` | Catch chain breaks early |
| 4. Test Upgrade | `python cli.py migrate --postgres-db <db>` | Ensure it applies |
| 5. Test Rollback | `python cli.py rollback --postgres-db <db>` | Ensure downgrade works |
| 6. Test Re-apply | `python cli.py migrate --postgres-db <db>` | Final confidence check |
| 7. Commit & Push | `git add . && git commit ...` | Pre-commit hook validates |
| 8. PR Review | Check checklist above | Human review |
| 9. Merge | Deploy runs `cli.py migrate` | Applied in production |

---

## See Also

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- `infrastructure/databases/cli.py` — CLI wrapper around Alembic
- `infrastructure/databases/migrations/postgres/alembic/` — All migration files
- `infrastructure/databases/migrations/postgres/alembic/env.py` — Alembic configuration
- `scripts/validate-migrations.py` — Migration validation tool

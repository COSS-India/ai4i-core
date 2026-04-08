#!/usr/bin/env python3
"""Run billing_v2_schema_migration.sql against Postgres (one DB per section)."""
from __future__ import annotations

import os
import sys

import psycopg2
import sqlparse

MIGRATION_SQL = os.path.join(os.path.dirname(__file__), "billing_v2_schema_migration.sql")

# Postgres credentials: set POSTGRES_* from your env / services/policy-engine/.env.
# (Welcome@123 or similar is for sudo on the host — not the database user password.)
DEFAULTS = {
    "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    "port": int(os.environ.get("POSTGRES_PORT", "5434")),
    "user": os.environ.get("POSTGRES_USER", "ai4i_user"),
    "password": os.environ.get("POSTGRES_PASSWORD", "ai4i_secure_password_2024"),
}


def load_sections(path: str) -> tuple[str, str, str]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    marker2 = "-- -----------------------------------------------------------------------------\n-- 2) Pay-per-use"
    marker3 = "-- -----------------------------------------------------------------------------\n-- 3) Multi-tenant"
    i2 = text.find(marker2)
    i3 = text.find(marker3)
    if i2 == -1 or i3 == -1:
        raise SystemExit("Could not find section markers in migration SQL")
    policy = text[:i2]
    pay = text[i2:i3]
    multi = text[i3:]
    return policy, pay, multi


def strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def run_statements(conn, sql_block: str, label: str) -> None:
    cleaned = strip_sql_comments(sql_block)
    parts = [p.strip() for p in sqlparse.split(cleaned) if p.strip()]
    conn.autocommit = True
    cur = conn.cursor()
    for i, stmt in enumerate(parts, 1):
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"[{label}] Statement {i}/{len(parts)} failed:\n{stmt[:200]}...\n{e}", file=sys.stderr)
            raise
    cur.close()
    print(f"[{label}] OK ({len(parts)} statements)")


def main() -> None:
    policy_sql, pay_sql, multi_sql = load_sections(MIGRATION_SQL)
    cfg = DEFAULTS.copy()

    dbs = [
        ("ai4i_platform", policy_sql, "policy"),
        ("pay_per_use_db", pay_sql, "pay_per_use"),
        ("multi_tenant_db", multi_sql, "multi_tenant"),
    ]
    for dbname, block, label in dbs:
        print(f"Connecting {dbname} @ {cfg['host']}:{cfg['port']} as {cfg['user']}...")
        conn = psycopg2.connect(dbname=dbname, **cfg)
        try:
            run_statements(conn, block, label)
        finally:
            conn.close()
    print("All sections completed.")


if __name__ == "__main__":
    main()

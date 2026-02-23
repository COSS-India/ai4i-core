#!/usr/bin/env python3
"""
Migration CLI
Laravel-like command-line interface for database migrations

Usage:
    python cli.py migrate [--database <db>] [--steps <n>]
    python cli.py rollback [--database <db>] [--steps <n>]
    python cli.py migrate:status [--database <db>]
    python cli.py migrate:fresh [--seed] [--database <db>]
    python cli.py make:migration <name> --database <db>
    python cli.py seed [--class <seeder>] [--database <db>]
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.databases.core.migration_manager import MigrationManager
from infrastructure.databases.config import MigrationConfig


class MigrationCLI:
    """Command-line interface for migrations"""
    
    DATABASES = ['postgres', 'redis', 'influxdb', 'elasticsearch', 'kafka']
    POSTGRES_DBS = [
        'auth_db', 
        'config_db', 
        'alerting_db',
        'metrics_db',
        'telemetry_db',
        'dashboard_db',
        'model_management_db', 
        'multi_tenant_db',
        'dhruva_platform'
    ]
    
    # External service databases (managed by third-party services, not our migration framework)
    EXTERNAL_DBS = [
        'unleash'  # Unleash feature flags - manages its own schema
    ]
    
    def __init__(self):
        self.migrations_path = project_root / 'infrastructure' / 'databases' / 'migrations'
        
    def run(self):
        """Run CLI"""
        parser = argparse.ArgumentParser(
            description='Database Migration Manager',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Run all pending migrations for all databases
  python cli.py migrate

  # Run migrations for specific database (avoids InfluxDB/ES/Kafka errors if not running)
  python cli.py migrate --database postgres
  python cli.py migrate --database postgres --postgres-db auth_db
  python cli.py migrate --database redis

  # Run specific number of migrations
  python cli.py migrate --database postgres --steps 3

  # Rollback last batch
  python cli.py rollback --database postgres

  # Rollback multiple batches
  python cli.py rollback --database postgres --steps 2

  # Check migration status
  python cli.py migrate:status
  python cli.py migrate:status --database postgres

  # Fresh migration (drop all and re-run)
  python cli.py migrate:fresh --database postgres
  python cli.py migrate:fresh --seed --database postgres
  python cli.py migrate:fresh:all --force
  python cli.py migrate:fresh:all --seed --force

  # Report DBs, tables, row counts
  python cli.py report

  # Initialize external service databases (e.g., Unleash)
  python cli.py init:external

  # Create new migration
  python cli.py make:migration create_users_table --database postgres

  # Run seeders
  python cli.py seed --database postgres
  python cli.py seed --class DefaultRolesSeeder --database postgres
            """
        )
        
        parser.add_argument('command', help='Command to run')
        parser.add_argument('name', nargs='?', help='Migration or seeder name (for make:migration)')
        parser.add_argument('--database', '-d', choices=self.DATABASES, help='Database type')
        parser.add_argument('--postgres-db', choices=self.POSTGRES_DBS, default='auth_db',
                          help='PostgreSQL database name (default: auth_db)')
        parser.add_argument('--steps', '-s', type=int, help='Number of steps')
        parser.add_argument('--class', '-c', dest='seeder_class', help='Seeder class name')
        parser.add_argument('--seed', action='store_true', help='Run seeders after migration')
        parser.add_argument('--force', '-y', action='store_true', dest='force',
                          help='Skip confirmation prompts (e.g. for migrate:fresh)')
        
        args = parser.parse_args()
        
        # Route to appropriate command
        command_map = {
            'migrate': self.migrate,
            'migrate:all': self.migrate_all,
            'rollback': self.rollback,
            'migrate:status': self.status,
            'migrate:fresh': self.fresh,
            'migrate:fresh:all': self.fresh_all,
            'make:migration': self.make_migration,
            'seed': self.seed,
            'seed:all': self.seed_all,
            'report': self.report,
            'init:external': self.init_external_databases,
        }
        
        if args.command not in command_map:
            print(f"❌ Unknown command: {args.command}")
            parser.print_help()
            sys.exit(1)
        
        # Execute command
        try:
            command_map[args.command](args)
        except KeyboardInterrupt:
            print("\n\n⚠️  Operation cancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def migrate(self, args):
        """Run migrations"""
        databases = [args.database] if args.database else self.DATABASES
        
        print("\n" + "=" * 80)
        print("🚀 Running Database Migrations")
        print("=" * 80)
        
        for db_type in databases:
            try:
                manager = self._get_manager(db_type, args.postgres_db if db_type == 'postgres' else None)
                manager.migrate(steps=args.steps)
            except Exception as e:
                print(f"❌ Error migrating {db_type}: {str(e)}")
        
        print("=" * 80)
        print("✅ Migration process completed!")
        print("=" * 80 + "\n")
    
    def rollback(self, args):
        """Rollback migrations"""
        if not args.database:
            print("❌ Please specify --database for rollback")
            sys.exit(1)
        
        print("\n" + "=" * 80)
        print(f"🔄 Rolling Back {args.database.upper()} Migrations")
        print("=" * 80)
        
        manager = self._get_manager(args.database, args.postgres_db if args.database == 'postgres' else None)
        manager.rollback(steps=args.steps or 1)
        
        print("=" * 80 + "\n")
    
    def status(self, args):
        """Show migration status"""
        databases = [args.database] if args.database else self.DATABASES
        
        print("\n" + "=" * 80)
        print("📊 Migration Status")
        print("=" * 80 + "\n")
        
        for db_type in databases:
            try:
                manager = self._get_manager(db_type, args.postgres_db if db_type == 'postgres' else None)
                manager.status()
            except Exception as e:
                print(f"❌ Error checking status for {db_type}: {str(e)}\n")
        
        print("=" * 80 + "\n")
    
    def fresh(self, args):
        """Fresh migration (drop all and re-run)"""
        if not args.database:
            print("❌ Please specify --database for fresh migration")
            sys.exit(1)
        
        # Confirmation unless --force / -y
        if not getattr(args, 'force', False):
            print("\n⚠️  WARNING: This will DROP ALL DATA in the database!")
            response = input(f"Are you sure you want to continue with {args.database}? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Operation cancelled")
                sys.exit(0)
        
        print("\n" + "=" * 80)
        print(f"🔨 Fresh Migration for {args.database.upper()}")
        if args.database == 'postgres':
            print(f"   Database: {args.postgres_db}")
        print("=" * 80)
        
        manager = self._get_manager(args.database, args.postgres_db if args.database == 'postgres' else None)
        manager.fresh(seed=args.seed)
        
        print("=" * 80 + "\n")

    def fresh_all(self, args):
        """Fresh migration for ALL Postgres DBs (clean + re-migrate), then optionally seed."""
        if not getattr(args, 'force', False):
            print("\n⚠️  WARNING: This will DROP ALL DATA in ALL Postgres databases!")
            response = input("Are you sure you want to continue? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Operation cancelled")
                sys.exit(0)
        
        print("\n" + "=" * 80)
        print("🔨 Fresh Migration for ALL Postgres Databases")
        print("=" * 80)
        
        failed = []
        for db in self.POSTGRES_DBS:
            try:
                print(f"\n  🗄️  Fresh: {db}...")
                manager = self._get_manager('postgres', db)
                manager.fresh(seed=False)
            except Exception as e:
                print(f"  ❌ Failed: {db} - {str(e)}")
                failed.append((db, str(e)))
        
        print("\n" + "=" * 80)
        if failed:
            print(f"⚠️  Fresh completed with {len(failed)} failure(s). Ensure PostgreSQL is running (e.g. localhost:5432, or 5434 if using docker-compose-simple.yml).")
            if len(failed) == len(self.POSTGRES_DBS):
                print("   No DB could be reached — is the Postgres server started?")
        else:
            print("✅ Fresh (clean + migrate) completed for all Postgres DBs!")
        print("=" * 80 + "\n")
        
        if getattr(args, 'seed', False) and not failed:
            print("🌱 Running seed:all...\n")
            self.seed_all(args)
    
    def make_migration(self, args):
        """Create new migration file"""
        if not args.name:
            print("❌ Please provide migration name")
            sys.exit(1)
        
        if not args.database:
            print("❌ Please specify --database")
            sys.exit(1)
        
        print("\n" + "=" * 80)
        print("📝 Creating New Migration")
        print("=" * 80 + "\n")
        
        manager = self._get_manager(args.database, args.postgres_db if args.database == 'postgres' else None)
        filepath = manager.make_migration(args.name)
        
        print(f"\n📄 Migration file created at:")
        print(f"   {filepath}\n")
        print("=" * 80 + "\n")
    
    def seed(self, args):
        """Run database seeders"""
        if not args.database:
            print("❌ Please specify --database for seeding")
            sys.exit(1)
        
        print("\n" + "=" * 80)
        print(f"🌱 Running {args.database.upper()} Seeders")
        print("=" * 80)
        
        manager = self._get_manager(args.database, args.postgres_db if args.database == 'postgres' else None)
        manager.seed(seeder_class=args.seeder_class)
        
        print("=" * 80 + "\n")
    
    def migrate_all(self, args):
        """Migrate all databases automatically"""
        print("\n" + "="*80)
        print("🚀 Migrating ALL Databases (Auto-Discovery)")
        print("="*80 + "\n")
        
        failed = []
        
        # Migrate all PostgreSQL databases
        print("📊 PostgreSQL Databases:")
        for db in self.POSTGRES_DBS:
            try:
                print(f"\n  🗄️  Migrating {db}...")
                manager = self._get_manager('postgres', db)
                manager.migrate()
            except Exception as e:
                print(f"  ❌ Failed: {db} - {str(e)}")
                failed.append(('postgres', db))
        
        # Migrate other databases
        print("\n📊 Other Databases:")
        for db in ['redis', 'influxdb', 'elasticsearch', 'kafka']:
            try:
                print(f"\n  🗄️  Migrating {db}...")
                manager = self._get_manager(db)
                manager.migrate()
            except Exception as e:
                print(f"  ❌ Failed: {db} - {str(e)}")
                failed.append((db, None))
        
        print("\n" + "="*80)
        if failed:
            print(f"⚠️  {len(failed)} database(s) failed:")
            for db_type, db_name in failed:
                print(f"  - {db_type}" + (f" ({db_name})" if db_name else ""))
        else:
            print("✅ All databases migrated successfully!")
        print("="*80 + "\n")
    
    def seed_all(self, args):
        """Seed all databases automatically"""
        print("\n" + "="*80)
        print("🌱 Seeding ALL Databases (Auto-Discovery)")
        print("="*80 + "\n")
        
        # Databases that have seeders
        postgres_dbs_with_seeders = [
            'auth_db', 'config_db', 'alerting_db',
            'dashboard_db', 'model_management_db', 'multi_tenant_db', 'dhruva_platform'
        ]
        
        # Seed PostgreSQL databases
        print("📊 PostgreSQL Databases:")
        for db in postgres_dbs_with_seeders:
            try:
                print(f"\n  🌱 Seeding {db}...")
                manager = self._get_manager('postgres', db)
                manager.seed()
            except Exception as e:
                print(f"  ⚠️  No seeders or failed: {db}")
        
        # Seed other databases
        print("\n📊 Other Databases:")
        for db in ['redis', 'influxdb']:
            try:
                print(f"\n  🌱 Seeding {db}...")
                manager = self._get_manager(db)
                manager.seed()
            except Exception as e:
                print(f"  ⚠️  No seeders or failed: {db}")
        
        print("\n" + "="*80)
        print("✅ Seeding completed!")
        print("="*80 + "\n")
    
    def report(self, args):
        """Report: how many Postgres DBs, tables per DB, and row counts."""
        print("\n" + "=" * 80)
        print("📊 Postgres Databases Report (tables + row counts)")
        print("=" * 80)
        
        total_dbs = 0
        total_tables = 0
        total_rows = 0
        
        for db in self.POSTGRES_DBS:
            try:
                manager = self._get_manager('postgres', db)
                with manager.adapter:
                    # List tables in public schema
                    tables_result = manager.adapter.fetch_all(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
                    )
                    tables = [r[0] for r in tables_result]
                    total_dbs += 1
                    db_rows = 0
                    
                    if not tables:
                        print(f"\n  📁 {db}: 0 tables, 0 rows")
                        continue
                    
                    print(f"\n  📁 {db}: {len(tables)} table(s)")
                    for t in tables:
                        try:
                            r = manager.adapter.fetch_one(f'SELECT count(*) FROM "{t}"')
                            cnt = r[0] if r else 0
                            db_rows += cnt
                            total_tables += 1
                            total_rows += cnt
                            print(f"      • {t}: {cnt} row(s)")
                        except Exception as e:
                            print(f"      • {t}: error ({e})")
                    print(f"      ─────────────────────")
                    print(f"      Subtotal: {len(tables)} tables, {db_rows} rows")
            except Exception as e:
                print(f"\n  ⚠️  {db}: skip ({e})")
        
        print("\n" + "=" * 80)
        print(f"  Total: {total_dbs} database(s), {total_tables} table(s), {total_rows} row(s)")
        print("=" * 80 + "\n")

    def init_external_databases(self, args):
        """
        Initialize external service databases.
        These are third-party services (like Unleash) that manage their own schemas.
        This command only ensures the databases exist - the services handle their own migrations.
        """
        from infrastructure.databases.adapters import PostgresAdapter
        
        print("\n" + "=" * 80)
        print("🔨 Initializing External Service Databases")
        print("=" * 80)
        print()
        print("ℹ️  External services manage their own database schemas.")
        print("   This command only ensures the databases exist.")
        print()
        
        # Get postgres connection config (connect to 'postgres' database to create others)
        base_config = MigrationConfig.get_postgres_config('postgres')
        
        for db_name in self.EXTERNAL_DBS:
            print(f"📦 Database: {db_name}")
            
            try:
                # Use the adapter's built-in _ensure_database_exists()
                db_config = MigrationConfig.get_postgres_config(db_name)
                adapter = PostgresAdapter(db_config)
                
                # The connect() method will automatically create the database if it doesn't exist
                adapter.connect()
                adapter.disconnect()
                
                print(f"   ✅ Ready (schema managed by external service)")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
            
            print()
        
        print("=" * 80)
        print("✅ External database initialization completed!")
        print("=" * 80 + "\n")

    def _get_manager(self, database_type: str, postgres_db: str = None) -> MigrationManager:
        """
        Get migration manager for database type
        
        Args:
            database_type: Type of database
            postgres_db: PostgreSQL database name (for postgres only)
            
        Returns:
            MigrationManager instance
        """
        # Get configuration
        kwargs = {}
        if database_type == 'postgres' and postgres_db:
            kwargs['database'] = postgres_db
        
        config = MigrationConfig.get_config_for_database(database_type, **kwargs)
        
        # Get adapter
        adapter_class = MigrationConfig.get_adapter_class(database_type)
        adapter = adapter_class(config)
        
        # Create manager
        return MigrationManager(
            migrations_path=str(self.migrations_path),
            database_type=database_type,
            adapter=adapter,
            database_name=postgres_db  # Pass the specific database name
        )


def main():
    """Main entry point"""
    cli = MigrationCLI()
    cli.run()


if __name__ == '__main__':
    main()

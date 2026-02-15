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

  # Run migrations for specific database
  python cli.py migrate --database postgres
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
        
        args = parser.parse_args()
        
        # Route to appropriate command
        command_map = {
            'migrate': self.migrate,
            'migrate:all': self.migrate_all,
            'rollback': self.rollback,
            'migrate:status': self.status,
            'migrate:fresh': self.fresh,
            'make:migration': self.make_migration,
            'seed': self.seed,
            'seed:all': self.seed_all,
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
        
        # Confirmation
        print("\n⚠️  WARNING: This will DROP ALL DATA in the database!")
        response = input(f"Are you sure you want to continue with {args.database}? (yes/no): ")
        
        if response.lower() != 'yes':
            print("❌ Operation cancelled")
            sys.exit(0)
        
        print("\n" + "=" * 80)
        print(f"🔨 Fresh Migration for {args.database.upper()}")
        print("=" * 80)
        
        manager = self._get_manager(args.database, args.postgres_db if args.database == 'postgres' else None)
        manager.fresh(seed=args.seed)
        
        print("=" * 80 + "\n")
    
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
            'dashboard_db', 'multi_tenant_db', 'dhruva_platform'
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

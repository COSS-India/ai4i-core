#!/usr/bin/env python3
"""
Migration CLI
Direct Alembic wrapper for database migrations

Usage:
    python cli.py migrate [--postgres-db <db>]
    python cli.py rollback [--postgres-db <db>] [--steps <n>]
    python cli.py migrate:status [--postgres-db <db>]
    python cli.py migrate:fresh [--postgres-db <db>] [--force]
    python cli.py make:migration <name> --postgres-db <db>
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")
load_dotenv(
    project_root / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic" / ".env",
    override=True,
)


class MigrationCLI:
    """Alembic migration CLI wrapper"""

    POSTGRES_DBS = [
        'ai4iplatform_auth',
        'ai4iplatform_core',
        'config_db',
        'alerting_db',
        'policy_db',
        'ai4i_platform'
    ]

    def __init__(self):
        self.alembic_dir = project_root / 'infrastructure' / 'databases' / 'migrations' / 'postgres'

    def run(self):
        """Run CLI"""
        parser = argparse.ArgumentParser(
            description='Alembic Migration CLI',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Run all pending migrations
  python cli.py migrate --postgres-db ai4iplatform_auth

  # Run specific number of migrations
  python cli.py migrate --postgres-db ai4iplatform_auth --steps 3

  # Rollback last migration
  python cli.py rollback --postgres-db ai4iplatform_auth

  # Rollback multiple migrations
  python cli.py rollback --postgres-db ai4iplatform_auth --steps 2

  # Check migration status
  python cli.py migrate:status --postgres-db ai4iplatform_auth

  # Fresh migration (downgrade to base, then upgrade)
  python cli.py migrate:fresh --postgres-db ai4iplatform_auth --force

  # Create new migration
  python cli.py make:migration create_users_table --postgres-db ai4iplatform_auth

  # Migrate all databases
  python cli.py migrate:all
            """
        )

        parser.add_argument('command', help='Command to run')
        parser.add_argument('name', nargs='?', help='Migration name (for make:migration)')
        parser.add_argument('--postgres-db', choices=self.POSTGRES_DBS, default='ai4iplatform_auth',
                          help='PostgreSQL database name (default: ai4iplatform_auth)')
        parser.add_argument('--steps', '-s', type=int, help='Number of migrations')
        parser.add_argument('--force', '-y', action='store_true', dest='force',
                          help='Skip confirmation prompts')

        args = parser.parse_args()

        # Route to appropriate command
        command_map = {
            'migrate': self.migrate,
            'migrate:all': self.migrate_all,
            'rollback': self.rollback,
            'migrate:status': self.status,
            'migrate:fresh': self.fresh,
            'make:migration': self.make_migration,
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
        """Run migrations using Alembic"""
        print("\n" + "=" * 80)
        print(f"🚀 Running Migrations: {args.postgres_db}")
        print("=" * 80 + "\n")

        revision = f"+{args.steps}" if args.steps else "heads"
        self._run_alembic(['upgrade', revision], args.postgres_db)
        print("=" * 80)
        print("✅ Migration completed!\n")

    def rollback(self, args):
        """Rollback migrations using Alembic"""
        print("\n" + "=" * 80)
        print(f"🔄 Rolling Back: {args.postgres_db}")
        print("=" * 80 + "\n")

        steps = args.steps or 1
        revision = f"-{steps}"
        self._run_alembic(['downgrade', revision], args.postgres_db)

    def status(self, args):
        """Show migration status using Alembic"""
        print("\n" + "=" * 80)
        print(f"📊 Migration Status: {args.postgres_db}")
        print("=" * 80 + "\n")

        self._run_alembic(['current', '-v'], args.postgres_db)
        print()
        self._run_alembic(['history', '-v'], args.postgres_db)

    def fresh(self, args):
        """Fresh migration (downgrade to base, then upgrade)"""
        if not getattr(args, 'force', False):
            print("\n⚠️  WARNING: This will DROP ALL DATA in the database!")
            response = input(f"Are you sure you want to continue? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Operation cancelled")
                sys.exit(0)

        print("\n" + "=" * 80)
        print(f"🔨 Fresh Migration: {args.postgres_db}")
        print("=" * 80 + "\n")

        print("  Downgrading to base...")
        self._run_alembic(['downgrade', 'base'], args.postgres_db)

        print("\n  Upgrading to head...")
        self._run_alembic(['upgrade', 'head'], args.postgres_db)

        print("\n✅ Fresh migration completed!\n")

    def make_migration(self, args):
        """Create new migration using Alembic"""
        if not args.name:
            print("❌ Please provide migration name")
            sys.exit(1)

        print("\n" + "=" * 80)
        print("📝 Creating New Migration")
        print("=" * 80 + "\n")

        self._run_alembic(['revision', '--autogenerate', '-m', args.name], args.postgres_db)

    def migrate_all(self, args):
        """Migrate all databases"""
        print("\n" + "="*80)
        print("🚀 Migrating ALL Databases")
        print("="*80 + "\n")

        failed = []
        for db in self.POSTGRES_DBS:
            try:
                print(f"  🗄️  Migrating {db}...")
                revision = f"+{args.steps}" if args.steps else "head"
                self._run_alembic(['upgrade', revision], db, show_output=False)
                print(f"  ✅ {db}")
            except Exception as e:
                print(f"  ❌ {db}: {str(e)}")
                failed.append(db)

        print("\n" + "="*80)
        if failed:
            print(f"⚠️  {len(failed)} database(s) failed: {', '.join(failed)}")
        else:
            print("✅ All databases migrated successfully!")
        print("="*80 + "\n")

    def _run_alembic(self, cmd_args: list, postgres_db: str, show_output: bool = True):
        """Run Alembic command with database selection"""
        cmd = [
            sys.executable, '-m', 'alembic',
            '-c', str(self.alembic_dir / 'alembic.ini'),
            '-x', f'db={postgres_db}'
        ] + cmd_args

        result = subprocess.run(
            cmd,
            cwd=str(self.alembic_dir),
            capture_output=not show_output,
            text=True
        )

        if show_output:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            err_msg = result.stderr or "unknown error"
            raise Exception(f"Alembic failed: {err_msg}")


def main():
    """Main entry point"""
    cli = MigrationCLI()
    cli.run()


if __name__ == '__main__':
    main()

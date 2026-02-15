"""
Migration Manager
Core logic for running and managing migrations
"""
import importlib.util
import os
import sys
from pathlib import Path
from typing import List, Optional, Type
from datetime import datetime

from .base_migration import BaseMigration
from .base_seeder import BaseSeeder
from .base_adapter import BaseAdapter
from .version_tracker import VersionTracker


class MigrationManager:
    """Manages database migrations and seeders"""
    
    def __init__(self, migrations_path: str, database_type: str, adapter: BaseAdapter):
        """
        Initialize migration manager
        
        Args:
            migrations_path: Path to migrations directory
            database_type: Type of database (postgres, redis, etc.)
            adapter: Database adapter instance
        """
        self.migrations_path = Path(migrations_path)
        self.database_type = database_type
        self.adapter = adapter
        self.version_tracker = VersionTracker(adapter)
        
    def migrate(self, steps: Optional[int] = None) -> None:
        """
        Run pending migrations
        
        Args:
            steps: Optional number of migrations to run (None = all)
        """
        print(f"\n🚀 Running {self.database_type.upper()} migrations...")
        
        # Ensure tracking table exists
        self.version_tracker.ensure_tracking_table()
        
        # Get pending migrations
        pending = self._get_pending_migrations()
        
        if not pending:
            print(f"✅ No pending migrations for {self.database_type}")
            return
        
        # Limit by steps if specified
        if steps:
            pending = pending[:steps]
        
        # Get next batch number
        batch = self.version_tracker.get_next_batch_number()
        
        # Run migrations
        with self.adapter:
            for migration_file in pending:
                migration_class = self._load_migration(migration_file)
                migration = migration_class()
                
                try:
                    print(f"  ⏳ Running: {migration_file}")
                    migration.up(self.adapter)
                    self.version_tracker.record_migration(migration_file, batch)
                    print(f"  ✅ Migrated: {migration_file}")
                except Exception as e:
                    print(f"  ❌ Failed: {migration_file}")
                    print(f"     Error: {str(e)}")
                    raise
        
        print(f"\n✅ {self.database_type.upper()} migrations completed!\n")
    
    def rollback(self, steps: int = 1) -> None:
        """
        Rollback migrations
        
        Args:
            steps: Number of batches to rollback
        """
        print(f"\n🔄 Rolling back {self.database_type.upper()} migrations...")
        
        with self.adapter:
            for _ in range(steps):
                # Get last batch migrations
                last_batch_migrations = self.version_tracker.get_last_batch_migrations()
                
                if not last_batch_migrations:
                    print(f"✅ No migrations to rollback for {self.database_type}")
                    return
                
                # Rollback in reverse order
                for migration_file in reversed(last_batch_migrations):
                    migration_class = self._load_migration(migration_file)
                    migration = migration_class()
                    
                    try:
                        print(f"  ⏳ Rolling back: {migration_file}")
                        migration.down(self.adapter)
                        self.version_tracker.remove_migration(migration_file)
                        print(f"  ✅ Rolled back: {migration_file}")
                    except Exception as e:
                        print(f"  ❌ Failed: {migration_file}")
                        print(f"     Error: {str(e)}")
                        raise
        
        print(f"\n✅ {self.database_type.upper()} rollback completed!\n")
    
    def status(self) -> None:
        """Show migration status"""
        print(f"\n📊 {self.database_type.upper()} Migration Status:")
        print("=" * 80)
        
        with self.adapter:
            executed = set(self.version_tracker.get_executed_migrations())
            all_migrations = self._get_all_migration_files()
            
            if not all_migrations:
                print("  No migrations found")
                return
            
            for migration_file in all_migrations:
                status = "✅ Executed" if migration_file in executed else "⏳ Pending"
                print(f"  {status} - {migration_file}")
        
        print("=" * 80 + "\n")
    
    def fresh(self, seed: bool = False) -> None:
        """
        Drop all tables and re-run migrations
        
        Args:
            seed: Whether to run seeders after migration
        """
        print(f"\n🔨 Fresh migration for {self.database_type.upper()}...")
        print("⚠️  WARNING: This will drop all data!\n")
        
        # Rollback all migrations
        with self.adapter:
            executed = self.version_tracker.get_executed_migrations()
            
            for migration_file in reversed(executed):
                migration_class = self._load_migration(migration_file)
                migration = migration_class()
                
                try:
                    print(f"  ⏳ Dropping: {migration_file}")
                    migration.down(self.adapter)
                    self.version_tracker.remove_migration(migration_file)
                    print(f"  ✅ Dropped: {migration_file}")
                except Exception as e:
                    print(f"  ⚠️  Error dropping {migration_file}: {str(e)}")
        
        # Run all migrations
        self.migrate()
        
        # Run seeders if requested
        if seed:
            self.seed()
    
    def seed(self, seeder_class: Optional[str] = None) -> None:
        """
        Run database seeders
        
        Args:
            seeder_class: Optional specific seeder class to run
        """
        print(f"\n🌱 Running {self.database_type.upper()} seeders...")
        
        seeders_path = self.migrations_path.parent / "seeders" / self.database_type
        
        if not seeders_path.exists():
            print(f"✅ No seeders found for {self.database_type}")
            return
        
        with self.adapter:
            if seeder_class:
                # Run specific seeder
                seeder_file = f"{seeder_class}.py"
                seeder = self._load_seeder(seeders_path / seeder_file)()
                print(f"  ⏳ Running: {seeder_class}")
                seeder.run(self.adapter)
                print(f"  ✅ Seeded: {seeder_class}")
            else:
                # Run all seeders
                seeder_files = sorted([f for f in os.listdir(seeders_path) 
                                      if f.endswith('.py') and f != '__init__.py'])
                
                for seeder_file in seeder_files:
                    seeder = self._load_seeder(seeders_path / seeder_file)()
                    seeder_name = seeder_file.replace('.py', '')
                    print(f"  ⏳ Running: {seeder_name}")
                    seeder.run(self.adapter)
                    print(f"  ✅ Seeded: {seeder_name}")
        
        print(f"\n✅ {self.database_type.upper()} seeding completed!\n")
    
    def make_migration(self, name: str) -> str:
        """
        Create a new migration file
        
        Args:
            name: Name of the migration
            
        Returns:
            Path to created migration file
        """
        timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
        filename = f"{timestamp}_{name}.py"
        filepath = self.migrations_path / self.database_type / filename
        
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Create migration file from template
        template = self._get_migration_template(name)
        filepath.write_text(template)
        
        print(f"✅ Created migration: {filepath}")
        return str(filepath)
    
    def _get_pending_migrations(self) -> List[str]:
        """Get list of pending migration files"""
        executed = set(self.version_tracker.get_executed_migrations())
        all_migrations = self._get_all_migration_files()
        return [m for m in all_migrations if m not in executed]
    
    def _get_all_migration_files(self) -> List[str]:
        """Get all migration files for this database type"""
        db_path = self.migrations_path / self.database_type
        
        if not db_path.exists():
            return []
        
        files = [f for f in os.listdir(db_path) 
                if f.endswith('.py') and f != '__init__.py']
        return sorted(files)
    
    def _load_migration(self, filename: str) -> Type[BaseMigration]:
        """Load migration class from file"""
        filepath = self.migrations_path / self.database_type / filename
        
        spec = importlib.util.spec_from_file_location(
            filename.replace('.py', ''), 
            filepath
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        
        # Find migration class
        for item_name in dir(module):
            item = getattr(module, item_name)
            if (isinstance(item, type) and 
                issubclass(item, BaseMigration) and 
                item is not BaseMigration):
                return item
        
        raise ValueError(f"No migration class found in {filename}")
    
    def _load_seeder(self, filepath: Path) -> Type[BaseSeeder]:
        """Load seeder class from file"""
        spec = importlib.util.spec_from_file_location(
            filepath.stem, 
            filepath
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        
        # Find seeder class
        for item_name in dir(module):
            item = getattr(module, item_name)
            if (isinstance(item, type) and 
                issubclass(item, BaseSeeder) and 
                item is not BaseSeeder):
                return item
        
        raise ValueError(f"No seeder class found in {filepath}")
    
    def _get_migration_template(self, name: str) -> str:
        """Get migration file template"""
        class_name = ''.join(word.capitalize() for word in name.split('_'))
        
        return f'''"""
{name.replace('_', ' ').title()} Migration
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class {class_name}(BaseMigration):
    """Migration: {name.replace('_', ' ')}"""
    
    def up(self, adapter):
        """Run migration"""
        # TODO: Implement migration logic
        pass
    
    def down(self, adapter):
        """Rollback migration"""
        # TODO: Implement rollback logic
        pass
'''

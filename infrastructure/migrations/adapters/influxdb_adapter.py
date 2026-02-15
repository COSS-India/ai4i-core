"""
InfluxDB Database Adapter
Handles InfluxDB-specific migration operations
"""
from typing import Any, Dict, List, Optional
from influxdb_client import InfluxDBClient, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS

from infrastructure.migrations.core.base_adapter import BaseAdapter


class InfluxDBAdapter(BaseAdapter):
    """InfluxDB database adapter (v2.x)"""
    
    MIGRATIONS_BUCKET = "_migrations"
    MIGRATIONS_MEASUREMENT = "executed_migrations"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize InfluxDB adapter
        
        Args:
            config: Database configuration with keys:
                - url: InfluxDB URL
                - token: Authentication token
                - org: Organization name
                - bucket: Default bucket (optional)
        """
        super().__init__(config)
        self.client = None
        self.write_api = None
        self.query_api = None
        self.buckets_api = None
        
    def connect(self) -> None:
        """Establish InfluxDB connection"""
        self.client = InfluxDBClient(
            url=self.config['url'],
            token=self.config['token'],
            org=self.config['org']
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.buckets_api = self.client.buckets_api()
        self.connection = self.client
        
        # Verify connection
        self.client.ping()
    
    def disconnect(self) -> None:
        """Close InfluxDB connection"""
        if self.client:
            self.client.close()
    
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute InfluxDB query (Flux)
        
        Args:
            query: Flux query to execute
            params: Optional query parameters
            
        Returns:
            Query result
        """
        return self.query_api.query(query, org=self.config['org'])
    
    def create_migrations_table(self) -> None:
        """Create migrations tracking bucket"""
        # Check if migrations bucket exists
        bucket = self.buckets_api.find_bucket_by_name(self.MIGRATIONS_BUCKET)
        
        if not bucket:
            # Create migrations bucket with 1 year retention
            retention_rules = BucketRetentionRules(type="expire", every_seconds=31536000)
            self.buckets_api.create_bucket(
                bucket_name=self.MIGRATIONS_BUCKET,
                org=self.config['org'],
                retention_rules=retention_rules
            )
    
    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migrations"""
        try:
            query = f'''
            from(bucket: "{self.MIGRATIONS_BUCKET}")
                |> range(start: 0)
                |> filter(fn: (r) => r._measurement == "{self.MIGRATIONS_MEASUREMENT}")
                |> filter(fn: (r) => r._field == "migration_name")
                |> sort(columns: ["_time"])
            '''
            
            result = self.execute(query)
            migrations = []
            
            for table in result:
                for record in table.records:
                    migrations.append(record.get_value())
            
            return migrations
        except Exception:
            return []
    
    def record_migration(self, migration_name: str, batch: int) -> None:
        """Record a migration as executed"""
        from influxdb_client import Point
        from datetime import datetime
        
        point = Point(self.MIGRATIONS_MEASUREMENT) \
            .tag("batch", str(batch)) \
            .field("migration_name", migration_name) \
            .time(datetime.utcnow())
        
        self.write_api.write(
            bucket=self.MIGRATIONS_BUCKET,
            org=self.config['org'],
            record=point
        )
    
    def remove_migration(self, migration_name: str) -> None:
        """Remove a migration record"""
        from datetime import datetime, timedelta
        
        # InfluxDB deletion using delete API
        delete_api = self.client.delete_api()
        
        # Delete points with this migration name
        start = datetime(1970, 1, 1)
        stop = datetime.utcnow() + timedelta(days=1)
        
        delete_api.delete(
            start=start,
            stop=stop,
            predicate=f'_measurement="{self.MIGRATIONS_MEASUREMENT}" AND migration_name="{migration_name}"',
            bucket=self.MIGRATIONS_BUCKET,
            org=self.config['org']
        )
    
    def get_last_batch_number(self) -> int:
        """Get the last batch number"""
        try:
            query = f'''
            from(bucket: "{self.MIGRATIONS_BUCKET}")
                |> range(start: 0)
                |> filter(fn: (r) => r._measurement == "{self.MIGRATIONS_MEASUREMENT}")
                |> filter(fn: (r) => r._field == "migration_name")
                |> group(columns: ["batch"])
                |> max(column: "batch")
            '''
            
            result = self.execute(query)
            max_batch = 0
            
            for table in result:
                for record in table.records:
                    batch = int(record.values.get("batch", 0))
                    if batch > max_batch:
                        max_batch = batch
            
            return max_batch
        except Exception:
            return 0
    
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """Get migrations from a specific batch"""
        query = f'''
        from(bucket: "{self.MIGRATIONS_BUCKET}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "{self.MIGRATIONS_MEASUREMENT}")
            |> filter(fn: (r) => r._field == "migration_name")
            |> filter(fn: (r) => r.batch == "{batch}")
            |> sort(columns: ["_time"])
        '''
        
        result = self.execute(query)
        migrations = []
        
        for table in result:
            for record in table.records:
                migrations.append(record.get_value())
        
        return migrations
    
    # InfluxDB-specific helper methods
    
    def create_bucket(self, bucket_name: str, retention_days: int = 30) -> None:
        """
        Create a new bucket
        
        Args:
            bucket_name: Name of the bucket
            retention_days: Retention period in days
        """
        retention_rules = BucketRetentionRules(
            type="expire", 
            every_seconds=retention_days * 86400
        )
        self.buckets_api.create_bucket(
            bucket_name=bucket_name,
            org=self.config['org'],
            retention_rules=retention_rules
        )
    
    def delete_bucket(self, bucket_name: str) -> None:
        """
        Delete a bucket
        
        Args:
            bucket_name: Name of the bucket
        """
        bucket = self.buckets_api.find_bucket_by_name(bucket_name)
        if bucket:
            self.buckets_api.delete_bucket(bucket)
    
    def write_point(self, bucket: str, measurement: str, tags: Dict[str, str], 
                    fields: Dict[str, Any]) -> None:
        """
        Write a data point
        
        Args:
            bucket: Bucket name
            measurement: Measurement name
            tags: Tag dictionary
            fields: Field dictionary
        """
        from influxdb_client import Point
        from datetime import datetime
        
        point = Point(measurement)
        for tag_key, tag_value in tags.items():
            point = point.tag(tag_key, tag_value)
        for field_key, field_value in fields.items():
            point = point.field(field_key, field_value)
        point = point.time(datetime.utcnow())
        
        self.write_api.write(bucket=bucket, org=self.config['org'], record=point)

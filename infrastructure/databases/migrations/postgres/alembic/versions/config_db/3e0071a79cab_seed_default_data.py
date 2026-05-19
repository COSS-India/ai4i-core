"""seed_default_data

Revision ID: 3e0071a79cab
Revises: a3f1e2d4b8c9
Create Date: 2026-05-18 15:50:00.567842

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e0071a79cab'
down_revision: Union[str, None] = 'a3f1e2d4b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 8 default configurations
    op.execute(sa.text("""
        INSERT INTO configurations (key, value, environment, service_name)
        SELECT key, value, environment, service_name FROM (VALUES
            ('api.timeout',                  '30',   'development', 'api-gateway-service'),
            ('cache.ttl',                    '300',  'development', 'api-gateway-service'),
            ('rate_limit.requests_per_minute','100', 'development', 'api-gateway-service'),
            ('jwt.expiry_minutes',           '15',   'development', 'auth-service'),
            ('jwt.refresh_expiry_days',      '7',    'development', 'auth-service'),
            ('metrics.retention_days',       '90',   'development', 'metrics-service'),
            ('alerts.cooldown_minutes',      '15',   'development', 'alerting-service'),
            ('dashboard.refresh_interval',   '30',   'development', 'dashboard-service')
        ) AS v(key, value, environment, service_name)
        WHERE NOT EXISTS (
            SELECT 1 FROM configurations c
            WHERE c.key = v.key
              AND c.environment = v.environment
              AND c.service_name = v.service_name
        )
    """))

    # 13 service registry entries
    op.execute(sa.text("""
        INSERT INTO service_registry (service_name, service_url, health_check_url, status, service_metadata)
        VALUES
            ('api-gateway-service', 'http://api-gateway-service:8080',  'http://api-gateway-service:8080/health',  'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('auth-service',        'http://auth-service:8081',         'http://auth-service:8081/health',         'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('config-service',      'http://config-service:8082',       'http://config-service:8082/health',       'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('metrics-service',     'http://metrics-service:8083',      'http://metrics-service:8083/health',      'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('telemetry-service',   'http://telemetry-service:8084',    'http://telemetry-service:8084/health',    'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('alerting-service',    'http://alerting-service:8085',     'http://alerting-service:8085/health',     'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('dashboard-service',   'http://dashboard-service:8086',    'http://dashboard-service:8086/health',    'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('asr-service',         '',                                  '',                                        'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('tts-service',         '',                                  '',                                        'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('nmt-service',         'http://nmt-service:8003',          'http://nmt-service:8003/health',          'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('llm-service',         'http://llm-service:8004',          'http://llm-service:8004/health',          'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('ocr-service',         'http://ocr-service:8005',          'http://ocr-service:8005/health',          'healthy', '{"version": "1.0.0", "environment": "development"}'),
            ('ner-service',         'http://ner-service:8006',          'http://ner-service:8006/health',          'healthy', '{"version": "1.0.0", "environment": "development"}')
        ON CONFLICT (service_name) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM service_registry
        WHERE service_name IN (
            'api-gateway-service','auth-service','config-service','metrics-service',
            'telemetry-service','alerting-service','dashboard-service','asr-service',
            'tts-service','nmt-service','llm-service','ocr-service','ner-service'
        )
    """))
    op.execute(sa.text("""
        DELETE FROM configurations
        WHERE (key, environment, service_name) IN (
            ('api.timeout',                   'development', 'api-gateway-service'),
            ('cache.ttl',                     'development', 'api-gateway-service'),
            ('rate_limit.requests_per_minute','development', 'api-gateway-service'),
            ('jwt.expiry_minutes',            'development', 'auth-service'),
            ('jwt.refresh_expiry_days',       'development', 'auth-service'),
            ('metrics.retention_days',        'development', 'metrics-service'),
            ('alerts.cooldown_minutes',       'development', 'alerting-service'),
            ('dashboard.refresh_interval',    'development', 'dashboard-service')
        )
    """))

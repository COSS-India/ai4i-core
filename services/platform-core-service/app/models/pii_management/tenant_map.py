"""ORM model for the pii_tenant_domain_map table."""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.models import Base


class TenantPiiDomainMap(Base):
    """Maps a tenant to its assigned PII redaction domain."""

    __tablename__ = "pii_tenant_domain_map"

    tenant_id  = Column(String(255), primary_key=True)
    domain_id  = Column(String(50),  nullable=False)
    created_at = Column(DateTime,   server_default=func.current_timestamp(), nullable=True)
    updated_at = Column(DateTime,   server_default=func.current_timestamp(), nullable=True)

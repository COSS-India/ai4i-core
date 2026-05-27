"""ORM model for the tenant_pii_domain_map table (PII database)."""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.models.pii_management import PiiBase


class TenantPiiDomainMap(PiiBase):
    """Maps a tenant to its assigned PII redaction domain."""

    __tablename__ = "tenant_pii_domain_map"

    tenant_id  = Column(String(255), primary_key=True)
    domain_id  = Column(String(50),  nullable=False)
    created_at = Column(DateTime,   server_default=func.current_timestamp(), nullable=True)
    updated_at = Column(DateTime,   server_default=func.current_timestamp(), nullable=True)

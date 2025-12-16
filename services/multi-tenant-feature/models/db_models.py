import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Column,String,DateTime,Enum,Integer,Boolean,text,ForeignKey,Numeric
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship

from .enum_tenant import TenantStatus , AuditAction ,BillingStatus , AuditActorType
from db_connection import TenantDBBase


def default_expiry():
    return (datetime.utcnow() + timedelta(days=365))

class Tenant(TenantDBBase):
    __tablename__ = "tenants"  # master tenants table (single schema: public)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(String(255), unique=True, nullable=False)  # user/provided id
    organization_name = Column(String(255), nullable=False)
    contact_email = Column(String(320), nullable=False, index=True)
    domain = Column(String(255), unique=True, nullable=False)  # user-provided domain e.g. acme.com
    subdomain = Column(String(255), unique=True, nullable=False)  # generated: acme.ai4i.com

    schema_name = Column(String(255), unique=True, nullable=False) # generated DB schema name

    # subscriptions: list of services e.g. ["tts", "asr", "nmt"]
    subscriptions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status = Column(Enum(TenantStatus, native_enum=False, create_type=False), nullable=False, default=TenantStatus.PENDING)

    # quotas and usage metadata
    quotas = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))  # e.g. {"api_calls_per_day":10000, "storage_gb":10}
    usage = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")) # e.g. {"api_calls_today":500, "storage_used_gb":2.5}

    # admin credentials placeholder
    temp_admin_username = Column(String(128), nullable=True)
    temp_admin_password_hash = Column(String(512), nullable=True)

    expiry_date = Column(TIMESTAMP(timezone=False), nullable=True, default=default_expiry)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    billing_record = relationship("BillingRecord", back_populates="tenant", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
    tenant_email_verifications = relationship("TenantEmailVerification", back_populates="tenant", cascade="all, delete-orphan")

    
    def __repr__(self):
        return f"<Tenant id={self.tenant_id} subdomain={self.subdomain} status={self.status}>"
    

class BillingRecord(TenantDBBase):
    __tablename__ = "tenant_billing_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    billing_customer_id = Column(String(255), nullable=True)  # external billing id
    billing_plan = Column(Numeric(10, 2), nullable=False, default=0.00)
    billing_status = Column(Enum(BillingStatus, native_enum=False, create_type=False),nullable=False,default=BillingStatus.UNPAID)
    suspension_reason = Column(String(512), nullable=True)
    suspended_until = Column(TIMESTAMP(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="billing_record")


class AuditLog(TenantDBBase):
    __tablename__ = "tenant_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(Enum(AuditAction, native_enum=False, create_type=False), nullable=False)
    actor = Column(Enum(AuditActorType, native_enum=False, create_type=False),nullable=False,default=AuditActorType.SYSTEM)  # who performed action (system, admin, billing)
    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog action={self.action} tenant={self.tenant_id}>"
    


class TenantEmailVerification(TenantDBBase):
    __tablename__ = "tenant_email_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(512), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="tenant_email_verifications")

    def __repr__(self):
        return f"<TenantEmailVerification tenant={self.tenant_id} verified_at={self.verified_at}>"

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Column,String,DateTime,Enum,Integer,Boolean,text,ForeignKey,Numeric,Date,BigInteger
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship

from .enum_tenant import TenantStatus , AuditAction ,BillingStatus , AuditActorType , ServiceUnitType , TenantUserStatus
from db_connection import TenantDBBase


def default_expiry():
    return (datetime.utcnow() + timedelta(days=365))

class Tenant(TenantDBBase):
    __tablename__ = "tenants"  # master tenants table (single schema: public)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(String(255), unique=True, nullable=False)  # user/provided id
    organization_name = Column(String(255), nullable=False)
    contact_email = Column(String(500), nullable=False, index=True)  # encrypted email can be longer
    phone_number = Column(String(500), nullable=True)  # encrypted phone number can be longer
    domain = Column(String(255), unique=True, nullable=False)  # user-provided domain e.g. acme.com
    # subdomain = Column(String(255), unique=True, nullable=False)  # generated: acme.ai4i.com

    schema_name = Column(String(255), unique=True, nullable=False) # generated DB schema name

    user_id = Column(Integer, nullable=True, index=True)  # References users.id in auth_db

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
    user_billing_records = relationship("UserBillingRecord", back_populates="tenant", cascade="all, delete-orphan")
    tenant_users = relationship("TenantUser", back_populates="tenant",foreign_keys="TenantUser.tenant_uuid", cascade="all, delete-orphan")

    
    def __repr__(self):
        return f"<Tenant id={self.tenant_id} status={self.status}>"
    

class BillingRecord(TenantDBBase):
    __tablename__ = "tenant_billing_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    billing_customer_id = Column(String(255), nullable=True)  # external billing id
    cost = Column(Numeric(20, 10), nullable=False, default=0.00)
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
    action = Column(Enum(AuditAction, native_enum=False, create_type=False,length=50),nullable=False)
    actor = Column(Enum(AuditActorType, native_enum=False, create_type=False,length=50),nullable=False,default=AuditActorType.SYSTEM)  # who performed action (system, admin, billing)
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
    


class ServiceConfig(TenantDBBase):
    __tablename__ = "service_config"

    id = Column(BigInteger, primary_key=True) 
    service_name = Column(String(50), unique=True, nullable=False)  # asr, tts, nmt
    unit_type = Column(Enum(ServiceUnitType, native_enum=False,length=50), nullable=False) # char, second, request
    price_per_unit = Column(Numeric(10, 6), nullable=False)         # 0.010
    currency = Column(String(10), default="INR")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_billing_records = relationship("UserBillingRecord" , back_populates="service_config")



class TenantUser(TenantDBBase):
    __tablename__ = "tenant_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    # user id from auth DB
    user_id = Column(Integer, nullable=False, index=True)
    tenant_uuid = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String(255),ForeignKey("tenants.tenant_id", ondelete="CASCADE"),nullable=False,index=True)
    username = Column(String(255), nullable=False)
    email = Column(String(500), nullable=False, index=True)  # encrypted email can be longer
    phone_number = Column(String(500), nullable=True)  # encrypted phone number can be longer
    subscriptions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_approved = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(TenantUserStatus, native_enum=False, create_type=False), nullable=False, default=TenantStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="tenant_users" , foreign_keys=[tenant_uuid])
    billing_records = relationship("UserBillingRecord",back_populates="tenant_users",cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TenantUser email={self.email} tenant_id={self.tenant_id}> user_id={self.user_id}"



class UserBillingRecord(TenantDBBase):
    __tablename__ = "user_billing_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id",ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    service_name = Column(String(50), nullable=False)
    service_id = Column(BigInteger, ForeignKey("service_config.id"), nullable=False)
    cost = Column(Numeric(20, 10), nullable=False, default=0.00)
    billing_period = Column(Date, nullable=False)  # 2025-12
    status = Column(Enum(TenantUserStatus, native_enum=False, create_type=False), nullable=False, default=TenantStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    service_config = relationship("ServiceConfig", back_populates="user_billing_records")
    tenant = relationship("Tenant", back_populates="user_billing_records")
    tenant_users = relationship("TenantUser", back_populates="billing_records")

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum,
    Integer,
    Boolean,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func, text


class TenantStatus(enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class TenantUserStatus(enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


TenantDBBase = declarative_base()


def default_expiry():
    return datetime.utcnow() + timedelta(days=365)


class Tenant(TenantDBBase):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(String(255), unique=True, nullable=False)
    organization_name = Column(String(255), nullable=False)
    contact_email = Column(String(500), nullable=False, index=True)
    phone_number = Column(String(500), nullable=True)
    domain = Column(String(255), unique=True, nullable=False)

    schema_name = Column(String(255), unique=True, nullable=False)

    # user id from auth DB
    user_id = Column(Integer, nullable=True, index=True)

    subscriptions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status = Column(
        Enum(TenantStatus, native_enum=False, create_type=False),
        nullable=False,
        default=TenantStatus.PENDING,
    )

    quotas = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    usage = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    temp_admin_username = Column(String(128), nullable=True)
    temp_admin_password_hash = Column(String(512), nullable=True)

    expiry_date = Column(TIMESTAMP(timezone=False), nullable=True, default=default_expiry)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant_users = relationship("TenantUser", back_populates="tenant", foreign_keys="TenantUser.tenant_uuid")


class TenantUser(TenantDBBase):
    __tablename__ = "tenant_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    # user id from auth DB
    user_id = Column(Integer, nullable=False, index=True)
    tenant_uuid = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)

    username = Column(String(255), nullable=False)
    email = Column(String(500), nullable=False, index=True)
    phone_number = Column(String(500), nullable=True)

    subscriptions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_approved = Column(Boolean, nullable=False, default=False)
    status = Column(
        Enum(TenantUserStatus, native_enum=False, create_type=False),
        nullable=False,
        default=TenantUserStatus.PENDING,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="tenant_users", foreign_keys=[tenant_uuid])


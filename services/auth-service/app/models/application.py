import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class ApplicationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index('uq_applications_tenant_name_lower', 'tenant_id', text('lower(name)'), unique=True),
    )

    # Integer PK (not UUID) — intentional; API schemas and routes must expose this as int.
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    domain = Column(String(255), nullable=True)
    allocated_percentage = Column(Numeric(5, 2), nullable=True)
    allocated_budget = Column(Numeric(15, 8), nullable=True)
    status = Column(
        Enum(
            ApplicationStatus,
            name="application_status_enum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=ApplicationStatus.ACTIVE.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    tenant = relationship("Tenant", back_populates="applications")
    api_keys = relationship("APIKey", back_populates="application", cascade="all, delete-orphan")

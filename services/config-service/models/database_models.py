from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class Configuration(Base):
    __tablename__ = "configurations"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    environment = Column(String(50), nullable=False)
    service_name = Column(String(100), nullable=False)
    is_encrypted = Column(Boolean, default=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    history = relationship("ConfigurationHistory", back_populates="configuration", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Configuration id={self.id} key={self.key} env={self.environment} service={self.service_name} version={self.version}>"


class ServiceRegistry(Base):
    __tablename__ = "service_registry"

    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False, unique=True)
    service_url = Column(String(255), nullable=False)
    health_check_url = Column(String(255))
    status = Column(String(20), default="unknown")
    last_health_check = Column(DateTime(timezone=True))
    service_metadata = Column(JSON)
    registered_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ServiceRegistry id={self.id} service={self.service_name} status={self.status}>"


class ConfigurationHistory(Base):
    __tablename__ = "configuration_history"

    id = Column(Integer, primary_key=True)
    configuration_id = Column(Integer, ForeignKey("configurations.id", ondelete="CASCADE"))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_by = Column(String(100))
    changed_at = Column(DateTime(timezone=True))

    configuration = relationship("Configuration", back_populates="history")

    def __repr__(self) -> str:
        return f"<ConfigurationHistory id={self.id} configuration_id={self.configuration_id}>"



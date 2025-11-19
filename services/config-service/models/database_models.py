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
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import declarative_base, relationship, foreign


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


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint('name', 'environment', name='uq_feature_flags_name_environment'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_enabled = Column(Boolean, default=False)
    rollout_percentage = Column(String(255))
    target_users = Column(JSON)
    environment = Column(String(50), nullable=False)
    unleash_flag_name = Column(String(255))
    last_synced_at = Column(DateTime(timezone=True))
    evaluation_count = Column(Integer, default=0)
    last_evaluated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FeatureFlag id={self.id} name={self.name} env={self.environment}>"


class FeatureFlagEvaluation(Base):
    __tablename__ = "feature_flag_evaluations"

    id = Column(Integer, primary_key=True)
    flag_name = Column(String(255), nullable=False)
    user_id = Column(String(255))
    context = Column(JSON)
    result = Column(Boolean, nullable=True)
    variant = Column(String(100))
    evaluated_value = Column(JSON)
    environment = Column(String(50), nullable=False)
    evaluated_at = Column(DateTime(timezone=True))
    evaluation_reason = Column(String(50))

    def __repr__(self) -> str:
        return f"<FeatureFlagEvaluation id={self.id} flag_name={self.flag_name}>"


# Configure relationships after both classes are defined
FeatureFlag.evaluations = relationship(
    "FeatureFlagEvaluation",
    back_populates="flag",
    cascade="all, delete-orphan",
    primaryjoin=and_(
        FeatureFlag.name == foreign(FeatureFlagEvaluation.flag_name),
        FeatureFlag.environment == foreign(FeatureFlagEvaluation.environment)
    ),
)

FeatureFlagEvaluation.flag = relationship(
    "FeatureFlag",
    back_populates="evaluations",
    primaryjoin=and_(
        foreign(FeatureFlagEvaluation.flag_name) == FeatureFlag.name,
        foreign(FeatureFlagEvaluation.environment) == FeatureFlag.environment
    ),
)



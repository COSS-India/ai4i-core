"""
Configuration management for Model Management Service.
Loads settings from environment variables with defaults.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    SERVICE_NAME: str = "model-management-service"
    SERVICE_PORT: int = 8091
    LOG_LEVEL: str = "INFO"
    
    # Database configuration
    APP_DB_USER: str = "dhruva_user"
    APP_DB_PASSWORD: str = "dhruva_secure_password_2024"
    APP_DB_HOST: str = "postgres"
    APP_DB_PORT: int = 5432
    APP_DB_NAME: str = "model_management_db"
    
    AUTH_DB_USER: str = "dhruva_user"
    AUTH_DB_PASSWORD: str = "dhruva_secure_password_2024"
    AUTH_DB_HOST: str = "postgres"
    AUTH_DB_PORT: int = 5432
    AUTH_DB_NAME: str = "auth_db"
    AUTH_SERVICE_URL: str = "http://auth-service:8081"
    
    # Redis configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Authentication flags
    AUTH_ENABLED: bool = True
    REQUIRE_API_KEY: bool = True
    ALLOW_ANONYMOUS_ACCESS: bool = False
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Version management configuration
    MAX_ACTIVE_VERSIONS_PER_MODEL: int = 5
    DEFAULT_VERSION_STATUS: str = "active"
    ENABLE_VERSION_IMMUTABILITY: bool = True
    ALLOW_SERVICE_DEPRECATED_VERSION_SWITCH: bool = False
    WARN_ON_DEPRECATED_VERSION_USAGE: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Singleton settings instance
settings = Settings()


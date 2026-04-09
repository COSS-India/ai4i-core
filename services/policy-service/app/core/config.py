from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "policy-service"
    host: str = "0.0.0.0"
    port: int = 8099
    log_level: str = "info"
    # Schema management:
    # - In production, prefer Alembic migrations (do NOT auto-create tables).
    # - Set AUTO_CREATE_TABLES=true only for local/dev convenience (e.g. SQLite).
    auto_create_tables: bool = False

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


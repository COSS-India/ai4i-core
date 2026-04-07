from functools import lru_cache
from pydantic_settings import BaseSettings


class DBSettings(BaseSettings):
    database_url: str = "sqlite:///./policy.db"

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache(maxsize=1)
def get_db_settings() -> DBSettings:
    return DBSettings()


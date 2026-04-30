"""Application settings: loads optional `.env` from the pay-per-use service root only."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .../services/pay-per-use-service (parent of `app/`)
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _SERVICE_ROOT / ".env"

_cfg: dict = {
    "env_file_encoding": "utf-8",
    "extra": "ignore",
}
if _DOTENV_PATH.is_file():
    # Single env file at service root; no template/cascading env files.
    _cfg["env_file"] = _DOTENV_PATH


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**_cfg)

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pay_per_use"
    redis_url: str = "redis://localhost:6379/0"
    policy_engine_url: str = "http://localhost:8095"
    multi_tenant_url: str = "http://localhost:8001"
    model_management_url: str = ""
    port: int = 8006


settings = Settings()

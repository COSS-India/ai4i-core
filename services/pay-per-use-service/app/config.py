from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pay_per_use"
    redis_url: str = "redis://localhost:6379/0"
    policy_engine_url: str = "http://localhost:8095"
    multi_tenant_url: str = "http://localhost:8001"
    model_management_url: str = ""
    port: int = 8006


settings = Settings()

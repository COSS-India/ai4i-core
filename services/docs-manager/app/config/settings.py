from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    service_version: str = "1.0.0"
    api_gateway_url: str
    services_host_suffix: str = ""

    @property
    def gateway_url(self) -> str:
        return self.api_gateway_url.rstrip("/")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

from pydantic_settings import BaseSettings


class AuthConfig(BaseSettings):
    """Environment-driven configuration for shared auth."""

    auth_enabled: bool = True
    require_api_key: bool = True
    allow_anonymous: bool = False
    auth_service_url: str = "http://auth-service:8081"
    auth_http_timeout: float = 5.0
    jwt_secret_key: str = "dhruva-jwt-secret-key-2024-super-secure"
    jwt_algorithm: str = "HS256"

    class Config:
        env_prefix = "AUTH_"
        case_sensitive = False


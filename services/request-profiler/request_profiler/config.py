"""Configuration management using pydantic-settings."""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Service metadata
    service_name: str = "translation-request-profiler"
    service_version: str = "1.0.0"
    environment: str = "development"

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 2
    log_level: str = "info"

    # Model paths
    model_dir: Path = Path("models")
    domain_model_path: Optional[Path] = None
    complexity_model_path: Optional[Path] = None
    fasttext_model_path: Optional[Path] = None
    spacy_model_name: str = "en_core_web_sm"
    common_words_path: Path = Path("data/common_words_10k.txt")

    # Performance settings
    max_text_length: int = 50_000
    min_text_words: int = 2
    request_timeout: int = 30
    max_batch_size: int = 50

    # Rate limiting
    rate_limit_per_minute: int = 100

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 8000

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default model paths if not provided
        if self.domain_model_path is None:
            self.domain_model_path = self.model_dir / "domain_pipeline.pkl"
        if self.complexity_model_path is None:
            self.complexity_model_path = self.model_dir / "complexity_regressor.pkl"
        if self.fasttext_model_path is None:
            # Try .ftz first (compressed), fall back to .bin
            ftz_path = self.model_dir / "lid.176.ftz"
            bin_path = self.model_dir / "lid.176.bin"
            self.fasttext_model_path = ftz_path if ftz_path.exists() else bin_path


# Global settings instance
settings = Settings()


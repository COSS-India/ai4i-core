"""Configuration for RequestProfiler"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Supported languages
    LANGUAGES: List[str] = ["hi", "bn", "ta", "te", "kn", "as"]
    LANGUAGE_NAMES: dict = {
        "hi": "Hindi",
        "bn": "Bengali",
        "ta": "Tamil",
        "te": "Telugu",
        "kn": "Kannada",
        "as": "Assamese"
    }
    
    # Model settings
    MODEL_PATH: str = "models/"
    COMPLEXITY_THRESHOLD: float = 5.0
    
    # API settings
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"


settings = Settings()

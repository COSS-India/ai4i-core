"""LLM service configuration."""

from ai4icore_env import app_env

# Re-export app_env for convenience — services use this for all config.
# Pay-per-use (LLM): see ``LLM_PPU_*`` and ``PAY_PER_USE_SERVICE_URL`` on ``app_env``.
settings = app_env

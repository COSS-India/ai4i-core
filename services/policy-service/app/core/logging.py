import logging
import os


def configure_logging(level: str = "info") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # Uvicorn access log can be noisy; respect NO_ACCESS_LOG if provided
    if os.getenv("NO_ACCESS_LOG", "false").lower() in {"1", "true", "yes"}:
        logging.getLogger("uvicorn.access").disabled = True


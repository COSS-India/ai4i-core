import logging
import sys

# -----------------------------
# Logging Configuration
# -----------------------------

def get_logger(name: str = __name__):
    """
    Configure and return a logger instance.

    Features:
      - Logs to stdout (so Docker/Kubernetes can capture logs)
      - Includes timestamp, log level, and module name
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if re-imported
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Global logger instance
logger = get_logger("multi-tenant-service")
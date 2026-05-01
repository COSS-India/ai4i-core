import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configuration
TARGET_BASE = os.getenv("TARGET_BASE", "https://staging.ai4inclusion.org")
PORT = int(os.getenv("PORT", 8080))
HOST = os.getenv("HOST", "127.0.0.1")

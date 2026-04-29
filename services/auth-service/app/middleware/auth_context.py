"""
Re-exports the shared ai4icore_auth.AuthMiddleware.

Auth-service uses the SAME middleware that every other microservice uses.
No local auth context logic — this file exists only as a clean import path.
"""

from ai4icore_auth.middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]

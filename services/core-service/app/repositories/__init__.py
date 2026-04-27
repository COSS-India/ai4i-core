"""Data access layer for core-service.

Each repository is a thin async wrapper around an AsyncSession with a
single-responsibility focus on its entity. Business rules live in the
service layer; repositories must remain free of cross-entity logic.
"""

"""
Repository layer for data access operations.

This module provides the data access layer following the Repository pattern,
separating business logic from data persistence concerns.
"""

from app.repositories.article_repository import ArticleRepository
from app.repositories.vector_repository import VectorRepository

__all__ = ['ArticleRepository', 'VectorRepository']

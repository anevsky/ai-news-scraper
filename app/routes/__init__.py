"""
Route layer for HTTP endpoints.

This module provides the controller/router layer handling HTTP requests
and responses, delegating to the service layer for business logic.
"""

from app.routes.articles import router as articles_router
from app.routes.search import router as search_router

__all__ = ['articles_router', 'search_router']

"""
Database models for the News Scraper application.

This module provides SQLAlchemy ORM models for storing and retrieving
news articles with AI-generated analysis.
"""

from app.models.article import Article, Base, init_db, get_session

__all__ = ['Article', 'Base', 'init_db', 'get_session']

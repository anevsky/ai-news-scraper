"""
Article Repository - Database Operations Layer

This module provides the data access layer for article operations, following the
Repository pattern to separate business logic from data access.

Responsibilities:
- CRUD operations for articles
- Keyword-based search (title, topic, content)
- Domain extraction utilities
- Database session management

The repository layer abstracts SQLAlchemy ORM operations and provides a clean API
for the service layer, making the codebase easier to test and maintain.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import urlparse
from sqlalchemy import desc, or_
from sqlalchemy.exc import IntegrityError

from app.models import Article, init_db, get_session

logger = logging.getLogger(__name__)


class ArticleRepository:
    """
    Repository for article database operations.

    This class encapsulates all database operations for articles, providing
    a clean interface that hides SQLAlchemy implementation details from the
    service layer.

    Design Pattern: Repository Pattern
    - Centralizes data access logic
    - Provides mockable interface for testing
    - Enables easy database migration if needed
    """

    @staticmethod
    def initialize_database():
        """
        Initialize database tables.

        Creates all tables defined in SQLAlchemy models if they don't exist.
        Safe to call multiple times (idempotent operation).

        Raises:
            Exception: If database initialization fails
        """
        try:
            init_db()
            logger.info("Database initialized successfully with SQLAlchemy")
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise

    @staticmethod
    def extract_domain(url: str) -> str:
        """
        Extract clean domain from URL for categorization.

        Examples:
            'https://www.techcrunch.com/article' -> 'techcrunch.com'
            'http://blog.example.co.uk/post' -> 'blog.example.co.uk'

        Args:
            url: Full article URL

        Returns:
            Clean domain name without 'www.' prefix
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except:
            return "unknown"

    @staticmethod
    def save_article(url: str, html_path: str, title: Optional[str] = None) -> Optional[int]:
        """
        Save initial scraped article metadata to database.

        This method is called after downloading the HTML but before AI analysis.
        It performs duplicate detection using the unique URL constraint.

        Args:
            url: Article URL (must be unique)
            html_path: Path to saved HTML file on disk
            title: Optional basic title extracted from HTML meta tags

        Returns:
            Article ID if successful, None if duplicate URL exists

        Example:
            >>> repo = ArticleRepository()
            >>> article_id = repo.save_article(
            ...     "https://example.com/article",
            ...     "downloaded_html/20250107_123456.html",
            ...     "Example Article Title"
            ... )
            >>> print(f"Saved article with ID: {article_id}")
        """
        session = get_session()
        try:
            article = Article(
                url=url,
                source_domain=ArticleRepository.extract_domain(url),
                scraped_date=datetime.now(),
                raw_html_path=html_path,
                title=title
            )
            session.add(article)
            session.commit()
            article_id = article.id
            logger.info(f"Saved article to database with ID: {article_id}, title: {title}")
            return article_id

        except IntegrityError:
            session.rollback()
            logger.warning(f"Duplicate article URL: {url}")
            return None
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving article: {str(e)}")
            return None
        finally:
            session.close()

    @staticmethod
    def update_article_analysis(
        url: str,
        article_data: dict,
        duration_ms: Optional[int] = None,
        tokens_used: Optional[int] = None
    ) -> bool:
        """
        Update article with AI analysis results from LLM.

        This method is called after LLM AI successfully extracts and analyzes
        the article content. It updates the article with:
        - Clean extracted content
        - AI-generated summary
        - AI-identified topics
        - Performance metrics (duration, token usage)

        Args:
            url: Article URL to update
            article_data: Dictionary containing:
                - title: LLM-extracted clean title
                - author: LLM-extracted author name
                - date: LLM-extracted publication date
                - summary: LLM-generated summary (2-3 sentences)
                - content: LLM-extracted clean article text
                - topics: LLM-identified topics (list of strings)
                - validation_warnings: Content quality warnings (optional)
            duration_ms: LLM API call duration in milliseconds (for performance tracking)
            tokens_used: Total tokens used in LLM analysis (for cost tracking)

        Returns:
            True if successful, False if article not found or update failed

        Example:
            >>> analysis = {
            ...     "title": "AI Breakthrough in Language Models",
            ...     "author": "Jane Smith",
            ...     "summary": "Researchers announce major advancement...",
            ...     "topics": ["AI", "Machine Learning", "NLP"]
            ... }
            >>> success = repo.update_article_analysis(
            ...     "https://example.com/article",
            ...     analysis,
            ...     duration_ms=2500,
            ...     tokens_used=4200
            ... )
        """
        session = get_session()
        try:
            article = session.query(Article).filter_by(url=url).first()

            if not article:
                logger.warning(f"Article not found for URL: {url}")
                return False

            # Update article fields with Claude analysis results
            article.title = article_data.get("title")
            article.author = article_data.get("author")
            article.published_date = article_data.get("date")
            article.analyzed_date = datetime.now()
            article.summary = article_data.get("summary")
            article.content = article_data.get("content")

            # Store topics as JSON string (Claude-identified themes)
            article.topics_json = json.dumps(article_data.get("topics", []))

            # Store validation warnings as JSON string
            article.validation_warnings_json = json.dumps(article_data.get("validation_warnings", []))

            # Store performance metrics
            article.analysis_duration_ms = duration_ms
            article.analysis_tokens = tokens_used

            session.commit()
            logger.info(f"Updated article analysis for URL: {url} (duration: {duration_ms}ms, tokens: {tokens_used})")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating article: {str(e)}")
            return False
        finally:
            session.close()

    @staticmethod
    def get_by_id(article_id: int) -> Optional[Dict]:
        """
        Retrieve article by ID.

        Args:
            article_id: Article ID

        Returns:
            Article dictionary or None if not found
        """
        session = get_session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                return article.to_dict()
            return None
        finally:
            session.close()

    @staticmethod
    def get_by_url(url: str) -> Optional[Dict]:
        """
        Retrieve article by URL for duplicate detection.

        Args:
            url: Article URL

        Returns:
            Article dictionary or None if not found
        """
        session = get_session()
        try:
            article = session.query(Article).filter_by(url=url).first()
            if article:
                return article.to_dict()
            return None
        finally:
            session.close()

    @staticmethod
    def get_all(limit: int = 100) -> List[Dict]:
        """
        Get all articles ordered by scraped date (newest first).

        Args:
            limit: Maximum number of articles to return (default 100)

        Returns:
            List of article dictionaries (without full content for performance)
        """
        session = get_session()
        try:
            articles = session.query(Article).order_by(desc(Article.scraped_date)).limit(limit).all()
            return [article.to_dict(include_content=False) for article in articles]
        finally:
            session.close()

    @staticmethod
    def get_analyzed_articles() -> List[Dict]:
        """
        Get all articles that have been analyzed by Claude AI.

        Only analyzed articles are eligible for semantic search since they
        need clean extracted content for embedding generation.

        Returns:
            List of analyzed article dictionaries with full content
        """
        session = get_session()
        try:
            articles = session.query(Article)\
                .filter(Article.content.isnot(None))\
                .order_by(desc(Article.analyzed_date))\
                .all()
            return [article.to_dict() for article in articles]
        finally:
            session.close()

    @staticmethod
    def search_by_title(query: str) -> List[Dict]:
        """
        Search articles by title using case-insensitive partial matching.

        This is part of the hybrid search system, providing keyword-based
        search that complements AI-powered semantic search.

        Args:
            query: Search query string

        Returns:
            List of matching articles

        Example:
            >>> results = repo.search_by_title("OpenAI")
            >>> # Returns articles with "OpenAI" anywhere in title
        """
        session = get_session()
        try:
            articles = session.query(Article)\
                .filter(Article.title.ilike(f"%{query}%"))\
                .order_by(desc(Article.scraped_date))\
                .all()
            return [article.to_dict(include_content=False) for article in articles]
        finally:
            session.close()

    @staticmethod
    def search_by_topic(query: str) -> List[Dict]:
        """
        Search articles by Claude-identified topics/tags.

        Topics are identified by Claude AI during analysis and stored as JSON.
        This enables search by themes like "AI", "Climate Change", etc.

        Args:
            query: Topic search string (case-insensitive)

        Returns:
            List of articles with matching topics

        Example:
            >>> results = repo.search_by_topic("Hardware")
            >>> # Returns articles with "Hardware" in their topics list
        """
        session = get_session()
        try:
            # Search in topics_json field (stored as JSON string)
            articles = session.query(Article)\
                .filter(Article.topics_json.ilike(f"%{query}%"))\
                .order_by(desc(Article.scraped_date))\
                .all()
            return [article.to_dict(include_content=False) for article in articles]
        finally:
            session.close()

    @staticmethod
    def search_by_content(query: str) -> List[Dict]:
        """
        Search articles by summary or full content.

        Performs case-insensitive search across both summary (AI-generated)
        and content (Claude-extracted clean article text).

        Args:
            query: Content search string

        Returns:
            List of articles with matching content
        """
        session = get_session()
        try:
            articles = session.query(Article)\
                .filter(
                    or_(
                        Article.summary.ilike(f"%{query}%"),
                        Article.content.ilike(f"%{query}%")
                    )
                )\
                .order_by(desc(Article.scraped_date))\
                .all()
            return [article.to_dict(include_content=False) for article in articles]
        finally:
            session.close()

    @staticmethod
    def delete(article_id: int) -> bool:
        """
        Delete article and cleanup associated HTML file.

        Args:
            article_id: Article ID to delete

        Returns:
            True if successful, False if article not found
        """
        session = get_session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()

            if not article:
                logger.warning(f"Article {article_id} not found")
                return False

            html_path = article.raw_html_path

            # Delete from database
            session.delete(article)
            session.commit()

            # Delete HTML file if exists
            if html_path and os.path.exists(html_path):
                try:
                    os.remove(html_path)
                    logger.info(f"Deleted HTML file: {html_path}")
                except Exception as e:
                    logger.warning(f"Could not delete HTML file {html_path}: {str(e)}")

            logger.info(f"Deleted article {article_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting article: {str(e)}")
            return False
        finally:
            session.close()

    @staticmethod
    def delete_all() -> bool:
        """
        Delete all articles and cleanup HTML files.

        Returns:
            True if successful, False otherwise
        """
        session = get_session()
        try:
            # Get all articles
            articles = session.query(Article).all()

            html_paths = [article.raw_html_path for article in articles]

            # Delete all from database
            session.query(Article).delete()
            session.commit()

            # Delete HTML files
            deleted_count = 0
            for html_path in html_paths:
                if html_path and os.path.exists(html_path):
                    try:
                        os.remove(html_path)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Could not delete HTML file {html_path}: {str(e)}")

            logger.info(f"Deleted all articles and {deleted_count} HTML files")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting all articles: {str(e)}")
            return False
        finally:
            session.close()

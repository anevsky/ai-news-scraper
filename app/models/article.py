"""
SQLAlchemy models for the news scraper application.

This module defines the database schema for storing scraped and analyzed news articles.
Articles are processed through two stages:
1. Scraping: Raw HTML is downloaded and basic metadata is saved
2. Analysis: LLM extracts and analyzes article content (title, author, summary, topics)
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional, List

Base = declarative_base()


class Article(Base):
    """
    Article model representing scraped and analyzed news articles.

    This model supports the full article lifecycle:
    - Initial scraping (saves URL, HTML path, basic title)
    - AI analysis with Claude (extracts clean content, generates summary, identifies topics)
    - Semantic search with OpenAI embeddings (stored in ChromaDB vector database)

    Attributes:
        id: Primary key
        url: Unique article URL (indexed for duplicate detection)
        source_domain: Domain extracted from URL (e.g., 'techcrunch.com')
        title: Article title
        author: Article author
        published_date: Original publication date
        scraped_date: When the article was scraped (indexed for chronological queries)
        analyzed_date: When the article was analyzed
        summary: Generated 2-3 sentence summary
        content: Full article text content (LLM-extracted, cleaned of ads/navigation)
        topics_json: JSON string of topics array (LLM-identified main themes)
        raw_html_path: Path to saved HTML file on disk
        validation_warnings_json: JSON string of content quality warnings
        analysis_duration_ms: Milliseconds taken for LLM API call (performance tracking)
        analysis_tokens: Total tokens used in LLM analysis (cost tracking)
        created_at: Timestamp of record creation
    """
    __tablename__ = 'articles'

    # Primary key and unique identifier
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False, index=True)

    # Source metadata
    source_domain = Column(String, index=True)

    # Article content (populated after analysis)
    title = Column(Text)
    author = Column(String)
    published_date = Column(String)

    # Lifecycle timestamps
    scraped_date = Column(DateTime, nullable=False, index=True)
    analyzed_date = Column(DateTime)

    # AI-generated content (Claude-powered)
    summary = Column(Text)  # Claude-generated summary
    content = Column(Text)  # Claude-extracted clean content
    topics_json = Column(Text)  # Claude-identified topics

    # Storage and validation
    raw_html_path = Column(Text)
    validation_warnings_json = Column(Text)

    # Performance and cost metrics
    analysis_duration_ms = Column(Integer)  # Claude API call duration
    analysis_tokens = Column(Integer)  # Claude API token usage

    # Record metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        """String representation for debugging."""
        return f"<Article(id={self.id}, title='{self.title[:50] if self.title else 'N/A'}...', source_domain='{self.source_domain}')>"

    @property
    def has_analysis(self) -> bool:
        """
        Check if article has been analyzed by Claude AI.

        An article is considered analyzed if it has extracted content.
        This determines whether the article is searchable via semantic search.

        Returns:
            True if article has been analyzed, False otherwise
        """
        return self.content is not None and len(self.content) > 0

    def to_dict(self, include_content: bool = True) -> dict:
        """
        Convert article to dictionary for API responses.

        This method provides a clean JSON-serializable representation of the article,
        handling datetime serialization and JSON field parsing.

        Args:
            include_content: Whether to include full content (can be large, >10KB)

        Returns:
            Dictionary representation of article with all metadata
        """
        import json

        data = {
            'id': self.id,
            'url': self.url,
            'source_domain': self.source_domain,
            'title': self.title,
            'author': self.author,
            'published_date': self.published_date,
            'scraped_date': self.scraped_date.isoformat() if self.scraped_date else None,
            'analyzed_date': self.analyzed_date.isoformat() if self.analyzed_date else None,
            'summary': self.summary,
            'has_analysis': self.has_analysis,
            'analysis_duration_ms': self.analysis_duration_ms,
            'analysis_tokens': self.analysis_tokens,
            'raw_html_path': self.raw_html_path,
        }

        # Include full content only if requested (can be large)
        if include_content:
            data['content'] = self.content

        # Parse JSON fields into Python objects
        if self.topics_json:
            try:
                data['topics'] = json.loads(self.topics_json)
            except:
                data['topics'] = []
        else:
            data['topics'] = []

        if self.validation_warnings_json:
            try:
                data['validation_warnings'] = json.loads(self.validation_warnings_json)
            except:
                data['validation_warnings'] = []
        else:
            data['validation_warnings'] = []

        return data


# Database configuration
# SQLite is used for structured data (article metadata, content)
# ChromaDB is used separately for vector embeddings (semantic search)
DATABASE_URL = "sqlite:///news_scraper.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Initialize database tables.

    Creates all tables defined in SQLAlchemy models if they don't exist.
    Safe to call multiple times (idempotent operation).
    """
    Base.metadata.create_all(bind=engine)


def get_session():
    """
    Get database session for ORM operations.

    Returns:
        SQLAlchemy session for querying and modifying the database

    Note:
        Caller is responsible for closing the session after use.
    """
    session = SessionLocal()
    try:
        return session
    finally:
        pass  # Session should be closed by caller

"""
Unit tests for database operations using the new repository architecture.

This test suite validates the ArticleRepository class which encapsulates
all database operations following the Repository Pattern.
"""

import pytest
import tempfile
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Article, get_session
from app.repositories import ArticleRepository


class TestArticleRepository:
    """Test suite for ArticleRepository."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Create a temporary test database for each test."""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()

        # Create test engine and session
        self.test_engine = create_engine(f'sqlite:///{self.temp_db.name}')
        Base.metadata.create_all(self.test_engine)
        self.SessionLocal = sessionmaker(bind=self.test_engine)

        # Patch get_session in BOTH models and repository modules
        import app.models.article as article_module
        import app.repositories.article_repository as repo_module

        self.original_article_get_session = article_module.get_session
        self.original_repo_get_session = repo_module.get_session

        # Create new session function
        def test_get_session():
            return self.SessionLocal()

        article_module.get_session = test_get_session
        repo_module.get_session = test_get_session

        # Create repository instance
        self.repo = ArticleRepository()

        yield

        # Cleanup
        article_module.get_session = self.original_article_get_session
        repo_module.get_session = self.original_repo_get_session
        os.unlink(self.temp_db.name)

    def test_save_article(self):
        """Test saving a scraped article."""
        url = "https://example.com/article1"
        html_path = "/tmp/test.html"
        title = "Test Article"

        article_id = self.repo.save_article(url, html_path, title)

        assert article_id is not None
        assert article_id > 0

        # Verify article was saved
        article = self.repo.get_by_id(article_id)
        assert article is not None
        assert article['url'] == url
        assert article['title'] == title
        assert article['has_analysis'] is False

    def test_save_duplicate_article(self):
        """Test that duplicate URLs are rejected."""
        url = "https://example.com/article1"
        html_path = "/tmp/test.html"

        # Save first time
        article_id_1 = self.repo.save_article(url, html_path, "Test 1")
        assert article_id_1 is not None

        # Try to save again with same URL
        article_id_2 = self.repo.save_article(url, html_path, "Test 2")
        assert article_id_2 is None  # Should return None for duplicate

    def test_update_article_analysis(self):
        """Test updating article with analysis results."""
        url = "https://example.com/article1"
        html_path = "/tmp/test.html"

        # First save the article
        article_id = self.repo.save_article(url, html_path, "Test")
        assert article_id is not None

        # Now update with analysis
        article_data = {
            'title': 'Analyzed Title',
            'author': 'John Doe',
            'date': '2025-01-01',
            'summary': 'Test summary',
            'content': 'Full article content here',
            'topics': ['Tech', 'AI'],
            'validation_warnings': []
        }

        result = self.repo.update_article_analysis(
            url, article_data, duration_ms=1000, tokens_used=500
        )
        assert result is True

        # Verify the update
        article = self.repo.get_by_id(article_id)
        assert article['title'] == 'Analyzed Title'
        assert article['author'] == 'John Doe'
        assert article['summary'] == 'Test summary'
        assert article['content'] == 'Full article content here'
        assert article['has_analysis'] is True
        assert article['analysis_duration_ms'] == 1000
        assert article['analysis_tokens'] == 500
        assert 'Tech' in article['topics']
        assert 'AI' in article['topics']

    def test_get_by_url(self):
        """Test retrieving article by URL."""
        url = "https://example.com/article1"
        article_id = self.repo.save_article(url, "/tmp/test.html", "Test")

        article = self.repo.get_by_url(url)
        assert article is not None
        assert article['id'] == article_id
        assert article['url'] == url

    def test_search_by_title(self):
        """Test title-based search."""
        # Create multiple articles
        self.repo.save_article("https://example.com/1", "/tmp/1.html", "Python Tutorial")
        self.repo.save_article("https://example.com/2", "/tmp/2.html", "JavaScript Guide")
        self.repo.save_article("https://example.com/3", "/tmp/3.html", "Python Advanced")

        # Search for Python
        results = self.repo.search_by_title("Python")
        assert len(results) == 2

        # Search for JavaScript
        results = self.repo.search_by_title("JavaScript")
        assert len(results) == 1

        # Case insensitive search
        results = self.repo.search_by_title("python")
        assert len(results) == 2

    def test_delete(self):
        """Test deleting an article."""
        url = "https://example.com/article1"
        article_id = self.repo.save_article(url, "/tmp/test.html", "Test")

        # Verify article exists
        article = self.repo.get_by_id(article_id)
        assert article is not None

        # Delete the article
        result = self.repo.delete(article_id)
        assert result is True

        # Verify it's deleted
        article = self.repo.get_by_id(article_id)
        assert article is None

    def test_get_all(self):
        """Test retrieving all articles."""
        # Create multiple articles
        self.repo.save_article("https://example.com/1", "/tmp/1.html", "Article 1")
        self.repo.save_article("https://example.com/2", "/tmp/2.html", "Article 2")
        self.repo.save_article("https://example.com/3", "/tmp/3.html", "Article 3")

        articles = self.repo.get_all()
        assert len(articles) == 3

    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        assert self.repo.extract_domain("https://www.techcrunch.com/article") == "techcrunch.com"
        assert self.repo.extract_domain("https://example.com/path") == "example.com"
        assert self.repo.extract_domain("http://subdomain.example.com/path") == "subdomain.example.com"

    def test_search_by_topic(self):
        """Test topic-based search."""
        # Create articles with topics
        url1 = "https://example.com/1"
        article_id1 = self.repo.save_article(url1, "/tmp/1.html", "Python Tutorial")

        article_data1 = {
            'title': 'Python Tutorial',
            'content': 'Learn Python',
            'summary': 'Python guide',
            'topics': ['Python', 'Programming', 'Tutorial'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url1, article_data1)

        url2 = "https://example.com/2"
        article_id2 = self.repo.save_article(url2, "/tmp/2.html", "JavaScript Guide")

        article_data2 = {
            'title': 'JavaScript Guide',
            'content': 'Learn JS',
            'summary': 'JS guide',
            'topics': ['JavaScript', 'Web Development'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url2, article_data2)

        # Search for Python topic
        results = self.repo.search_by_topic("Python")
        assert len(results) == 1
        assert results[0]['id'] == article_id1

        # Search for JavaScript topic
        results = self.repo.search_by_topic("JavaScript")
        assert len(results) == 1
        assert results[0]['id'] == article_id2

        # Case insensitive search
        results = self.repo.search_by_topic("programming")
        assert len(results) == 1

    def test_search_by_content(self):
        """Test content and summary-based search."""
        url1 = "https://example.com/1"
        article_id1 = self.repo.save_article(url1, "/tmp/1.html", "Article 1")

        article_data1 = {
            'title': 'Article 1',
            'content': 'This article discusses machine learning algorithms',
            'summary': 'A comprehensive guide',
            'topics': ['AI'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url1, article_data1)

        url2 = "https://example.com/2"
        article_id2 = self.repo.save_article(url2, "/tmp/2.html", "Article 2")

        article_data2 = {
            'title': 'Article 2',
            'content': 'Web development basics',
            'summary': 'Learn about neural networks and deep learning',
            'topics': ['Web'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url2, article_data2)

        # Search in content
        results = self.repo.search_by_content("machine learning")
        assert len(results) == 1
        assert results[0]['id'] == article_id1

        # Search in summary
        results = self.repo.search_by_content("neural networks")
        assert len(results) == 1
        assert results[0]['id'] == article_id2

        # Search term appears in both
        results = self.repo.search_by_content("learning")
        assert len(results) == 2

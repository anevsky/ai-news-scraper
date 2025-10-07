"""
Unit tests for hybrid search functionality using the new service architecture.

This test suite validates the SearchService class which implements
sophisticated hybrid search combining AI semantic search with keyword matching.
"""

import pytest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.repositories import ArticleRepository
from app.services import SearchService


class TestSearchService:
    """Test suite for SearchService hybrid search."""

    @pytest.fixture(autouse=True)
    def setup_test_search(self):
        """Set up test database and search service."""
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

        # Create service and repository instances
        self.service = SearchService()
        self.repo = ArticleRepository()

        yield

        # Cleanup
        article_module.get_session = self.original_article_get_session
        repo_module.get_session = self.original_repo_get_session
        os.unlink(self.temp_db.name)

    def test_hybrid_search_combines_results(self):
        """Test that hybrid search combines semantic and keyword results."""
        # Create test articles
        url1 = "https://example.com/python"
        self.repo.save_article(url1, "/tmp/1.html", "Python Tutorial")

        article_data1 = {
            'title': 'Python Programming Guide',
            'content': 'Learn Python programming',
            'summary': 'Python tutorial for beginners',
            'topics': ['Python', 'Programming'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url1, article_data1)

        url2 = "https://example.com/js"
        self.repo.save_article(url2, "/tmp/2.html", "JavaScript Guide")

        article_data2 = {
            'title': 'JavaScript Programming',
            'content': 'Learn JavaScript',
            'summary': 'JS guide',
            'topics': ['JavaScript'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url2, article_data2)

        # Search by title keyword
        main_results, suggestions = self.service.search("Python")

        # Should find Python article with high score (title match = 90%)
        assert len(main_results) >= 1
        python_article = next((r for r in main_results if "Python" in r['title']), None)
        assert python_article is not None
        assert python_article['similarity_score'] == 0.9  # Title match score

    def test_search_results_sorted_by_score(self):
        """Test that search results are sorted by relevance score."""
        # Create articles with different match types
        # Title match (90% score)
        url1 = "https://example.com/1"
        self.repo.save_article(url1, "/tmp/1.html", "Hardware Review")

        # Topic match (85% score)
        url2 = "https://example.com/2"
        self.repo.save_article(url2, "/tmp/2.html", "Tech News")
        article_data2 = {
            'title': 'Tech News',
            'content': 'Latest tech updates',
            'summary': 'Technology news',
            'topics': ['Hardware', 'Tech'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url2, article_data2)

        # Content match (70% score)
        url3 = "https://example.com/3"
        self.repo.save_article(url3, "/tmp/3.html", "General Article")
        article_data3 = {
            'title': 'General Article',
            'content': 'Article discusses hardware components',
            'summary': 'General tech article',
            'topics': ['Tech'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url3, article_data3)

        # Search for "Hardware"
        main_results, suggestions = self.service.search("Hardware")

        # Should return results in descending score order
        assert len(main_results) >= 2

        # Verify scores are in descending order
        for i in range(len(main_results) - 1):
            assert main_results[i]['similarity_score'] >= main_results[i + 1]['similarity_score']

        # Title match should be first (highest score)
        assert main_results[0]['title'] == "Hardware Review"
        assert main_results[0]['similarity_score'] == 0.9

    def test_relevance_threshold_filtering(self):
        """Test that results are filtered by relevance thresholds."""
        # Create articles with analyzed content
        url1 = "https://example.com/1"
        self.repo.save_article(url1, "/tmp/1.html", "Relevant Article")
        article_data1 = {
            'title': 'Relevant Article',
            'content': 'This article is about testing with mentions of the keyword',
            'summary': 'Article about testing',
            'topics': ['Testing', 'Software'],
            'author': 'Author',
            'date': '2025-01-01',
            'validation_warnings': []
        }
        self.repo.update_article_analysis(url1, article_data1)

        # Search for a term that appears in content (70% score)
        main_results, suggestions = self.service.search("testing")

        # Should appear in main results (>= 30% threshold)
        assert len(main_results) >= 1
        assert any('Testing' in r.get('topics', []) for r in main_results)

        # All main results should have score >= 0.3
        for result in main_results:
            assert result['similarity_score'] >= 0.3

        # All suggestions should have score between 0.2 and 0.3
        for suggestion in suggestions:
            assert 0.2 <= suggestion['similarity_score'] < 0.3

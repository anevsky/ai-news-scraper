"""
Unit tests for FastAPI route endpoints.

This test suite validates the HTTP endpoints using FastAPI's TestClient,
ensuring routes work correctly without needing to start the actual server.
"""

import pytest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.models import Base
from app.repositories import ArticleRepository
from main import app


class TestArticleRoutes:
    """Test suite for article-related routes."""

    @pytest.fixture(autouse=True)
    def setup_test_routes(self):
        """Set up test database and TestClient."""
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

        # Create TestClient
        self.client = TestClient(app)

        # Create repository instance
        self.repo = ArticleRepository()

        yield

        # Cleanup
        article_module.get_session = self.original_article_get_session
        repo_module.get_session = self.original_repo_get_session
        os.unlink(self.temp_db.name)

    def test_list_articles_api(self):
        """Test GET /api/articles endpoint."""
        # Create test articles
        self.repo.save_article("https://example.com/1", "/tmp/1.html", "Test Article 1")
        self.repo.save_article("https://example.com/2", "/tmp/2.html", "Test Article 2")

        # Call API
        response = self.client.get("/api/articles")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert len(data["articles"]) == 2
        assert data["articles"][0]["title"] == "Test Article 2"  # Most recent first
        assert data["articles"][1]["title"] == "Test Article 1"

    def test_get_article_by_id(self):
        """Test GET /api/article/{id} endpoint."""
        # Create test article
        article_id = self.repo.save_article(
            "https://example.com/test",
            "/tmp/test.html",
            "Test Article"
        )

        # Call API
        response = self.client.get(f"/api/article/{article_id}")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "article" in data
        assert data["article"]["id"] == article_id
        assert data["article"]["title"] == "Test Article"
        assert data["article"]["url"] == "https://example.com/test"

    def test_get_article_not_found(self):
        """Test GET /api/article/{id} with non-existent ID."""
        response = self.client.get("/api/article/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_article(self):
        """Test DELETE /api/article/{id} endpoint."""
        # Create test article
        article_id = self.repo.save_article(
            "https://example.com/delete",
            "/tmp/delete.html",
            "Delete Me"
        )

        # Verify it exists
        article = self.repo.get_by_id(article_id)
        assert article is not None

        # Delete via API
        response = self.client.delete(f"/api/article/{article_id}")
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

        # Verify it's deleted
        article = self.repo.get_by_id(article_id)
        assert article is None

    def test_health_check(self):
        """Test GET /health endpoint."""
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        # Health endpoint may or may not include timestamp, just check it returns valid JSON
        assert "app" in data or "timestamp" in data


class TestSearchRoutes:
    """Test suite for search-related routes."""

    @pytest.fixture(autouse=True)
    def setup_test_search_routes(self):
        """Set up test database and TestClient."""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()

        # Create test engine and session
        self.test_engine = create_engine(f'sqlite:///{self.temp_db.name}')
        Base.metadata.create_all(self.test_engine)
        self.SessionLocal = sessionmaker(bind=self.test_engine)

        # Patch get_session
        import app.models.article as article_module
        import app.repositories.article_repository as repo_module

        self.original_article_get_session = article_module.get_session
        self.original_repo_get_session = repo_module.get_session

        def test_get_session():
            return self.SessionLocal()

        article_module.get_session = test_get_session
        repo_module.get_session = test_get_session

        # Create TestClient
        self.client = TestClient(app)

        # Create repository
        self.repo = ArticleRepository()

        yield

        # Cleanup
        article_module.get_session = self.original_article_get_session
        repo_module.get_session = self.original_repo_get_session
        os.unlink(self.temp_db.name)

    def test_search_stats(self):
        """Test GET /api/search/stats endpoint."""
        # Create test articles
        self.repo.save_article("https://example.com/1", "/tmp/1.html", "Article 1")
        self.repo.save_article("https://example.com/2", "/tmp/2.html", "Article 2")

        # Call API
        response = self.client.get("/api/search/stats")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["total_articles"] == 2
        assert "embedding_model" in data
        assert "collection_name" in data

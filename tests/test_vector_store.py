"""
Unit tests for vector store operations using the new repository architecture.

This test suite validates the VectorRepository class which encapsulates
ChromaDB operations and OpenAI embeddings following the Repository Pattern.
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path

from app.repositories import VectorRepository


class TestVectorRepository:
    """Test suite for VectorRepository."""

    @pytest.fixture(autouse=True)
    def setup_test_vectordb(self):
        """Create a temporary ChromaDB for each test."""
        # Create temporary directory for ChromaDB
        self.temp_dir = tempfile.mkdtemp()

        # Create repository with test directory
        self.repo = VectorRepository()

        # Override the ChromaDB path
        import chromadb
        from chromadb.config import Settings
        self.repo.chroma_client = chromadb.PersistentClient(
            path=self.temp_dir,
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )

        yield

        # Cleanup
        shutil.rmtree(self.temp_dir)

    def test_add_article(self):
        """Test adding an article to vector database."""
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        article = {
            'id': 1,
            'title': 'Test Article About Python',
            'summary': 'This is a test article about Python programming',
            'topics': ['Python', 'Programming'],
            'content': 'Full content here',
            'url': 'https://example.com/test',
            'author': 'Test Author',
            'source_domain': 'example.com',
            'published_date': '2025-01-01',
            'scraped_date': '2025-01-01'
        }

        result = self.repo.add_article(article)
        assert result is True

        # Verify it was added
        stats = self.repo.get_stats()
        assert stats['count'] == 1

    def test_semantic_search(self):
        """Test semantic search functionality."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        # Add a test article
        article = {
            'id': 1,
            'title': 'Machine Learning Tutorial',
            'summary': 'Learn about neural networks and deep learning',
            'topics': ['AI', 'Machine Learning'],
            'content': 'Content about ML',
            'url': 'https://example.com/ml',
            'author': 'ML Expert',
            'source_domain': 'example.com',
            'published_date': '2025-01-01',
            'scraped_date': '2025-01-01'
        }

        self.repo.add_article(article)

        # Search for related terms
        results = self.repo.semantic_search('artificial intelligence', n_results=5)
        assert len(results) > 0
        assert results[0]['id'] == 1
        assert 0 <= results[0]['similarity_score'] <= 1
        assert results[0]['distance'] >= 0

    def test_similarity_score_calculation(self):
        """Test that similarity scores are properly normalized."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        article = {
            'id': 1,
            'title': 'Python Programming Guide',
            'summary': 'Comprehensive Python tutorial for beginners',
            'topics': ['Python', 'Tutorial'],
            'content': 'Learn Python',
            'url': 'https://example.com/python',
            'author': 'Expert',
            'source_domain': 'example.com',
            'published_date': '2025-01-01',
            'scraped_date': '2025-01-01'
        }

        self.repo.add_article(article)

        # Search with very similar query
        results = self.repo.semantic_search('Python programming tutorial', n_results=1)
        assert len(results) == 1

        score = results[0]['similarity_score']
        # Score should be high for very similar content
        assert 0 <= score <= 1, f"Score should be between 0 and 1, got {score}"

        # Distance should be between 0 and 2 (ChromaDB range)
        assert 0 <= results[0]['distance'] <= 2

    def test_delete_article(self):
        """Test deleting an article from vector database."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        article = {
            'id': 1,
            'title': 'Test Article',
            'summary': 'Test summary',
            'topics': ['Test'],
            'content': 'Content',
            'url': 'https://example.com/test',
            'author': 'Author',
            'source_domain': 'example.com',
            'published_date': '2025-01-01',
            'scraped_date': '2025-01-01'
        }

        self.repo.add_article(article)

        # Verify it was added
        stats = self.repo.get_stats()
        assert stats['count'] == 1

        # Delete it
        result = self.repo.delete_article(1)
        assert result is True

        # Verify it was deleted
        stats = self.repo.get_stats()
        assert stats['count'] == 0

    def test_get_stats(self):
        """Test getting collection statistics."""
        stats = self.repo.get_stats()
        assert 'count' in stats
        assert 'collection_name' in stats
        assert 'embedding_model' in stats
        assert stats['count'] == 0  # Empty database initially

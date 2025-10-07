"""
Vector Repository - Semantic Search Layer

This module provides the data access layer for vector database operations using ChromaDB
and OpenAI embeddings for semantic search.

Responsibilities:
- Generate embeddings using OpenAI's text-embedding-3-small model
- Store article vectors in ChromaDB for similarity search
- Perform semantic search with cosine similarity
- Manage vector database lifecycle (add, delete, stats)

GenAI Integration:
- OpenAI Embeddings API: Converts text to 1536-dimensional vectors
- ChromaDB: Persistent vector database for semantic similarity search
- Cosine Similarity: Measures semantic similarity between query and articles

Design Pattern: Repository Pattern
- Abstracts vector database operations
- Provides clean API for service layer
- Enables easy swap of vector DB provider if needed
"""

import chromadb
from chromadb.config import Settings
import logging
import os
from typing import List, Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# Vector database configuration
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "news_articles")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


class VectorRepository:
    """
    Repository for vector database operations using ChromaDB and OpenAI.

    This class implements semantic search functionality by:
    1. Converting text to vectors using OpenAI's embedding model
    2. Storing vectors in ChromaDB with article metadata
    3. Performing similarity search using cosine distance

    GenAI Technology Stack:
    - OpenAI text-embedding-3-small (1536 dimensions)
    - ChromaDB persistent vector database
    - Cosine similarity for semantic matching

    Design Considerations:
    - Lazy initialization of OpenAI client (for testing)
    - Persistent storage for vector data
    - Rich text embeddings (title + summary + topics)
    - Normalized similarity scores [0,1]
    """

    def __init__(self):
        """
        Initialize vector repository with ChromaDB client.

        ChromaDB is configured with:
        - Persistent storage in ./chroma_db directory
        - Telemetry disabled for privacy
        - Collection reset capability for testing
        """
        self._openai_client = None
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

    def get_openai_client(self) -> OpenAI:
        """
        Get or create OpenAI client (lazy initialization).

        Lazy initialization enables:
        - Tests to run without API key
        - Deferred API key validation
        - Better error handling

        Returns:
            Initialized OpenAI client

        Raises:
            ValueError: If OPENAI_API_KEY environment variable not set
        """
        if self._openai_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self._openai_client = OpenAI(api_key=api_key)
        return self._openai_client

    def get_collection(self):
        """
        Get or create ChromaDB collection for articles.

        The collection stores:
        - Article embeddings (1536-dimensional vectors)
        - Article metadata (title, author, topics, etc.)
        - Searchable text (title + summary + topics)

        Returns:
            ChromaDB collection instance
        """
        return self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "News articles with semantic search"}
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using OpenAI.

        This is the core of semantic search - converting text to a vector
        representation that captures meaning. Similar texts will have similar
        vectors (measured by cosine similarity).

        GenAI Technology: OpenAI text-embedding-3-small
        - Model: text-embedding-3-small (fast, cost-effective)
        - Dimensions: 1536
        - Cost: ~$0.02 per 1M tokens
        - Performance: Excellent for news article search

        Args:
            text: Text to convert to embedding vector

        Returns:
            1536-dimensional embedding vector

        Raises:
            Exception: If OpenAI API call fails

        Example:
            >>> repo = VectorRepository()
            >>> vector = repo.generate_embedding("AI breakthrough in language models")
            >>> len(vector)  # 1536
        """
        try:
            client = self.get_openai_client()
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding of length {len(embedding)} for text: {text[:50]}...")
            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    def add_article(self, article: Dict) -> bool:
        """
        Add article to vector database with semantic embeddings.

        This method implements the "rich embedding" strategy:
        - Combines title, summary, and topics into searchable text
        - Generates single embedding for the combined text
        - Stores metadata for retrieval

        The rich embedding approach improves search quality by:
        - Capturing article essence across multiple fields
        - Enabling topic-aware semantic search
        - Providing context beyond just title

        Args:
            article: Article dictionary with required fields:
                - id: Article ID
                - title: Article title (Claude-extracted)
                - summary: AI-generated summary
                - topics: AI-identified topics
                - url, author, source_domain, dates (metadata)

        Returns:
            True if successful, False otherwise

        Example:
            >>> article = {
            ...     "id": 123,
            ...     "title": "AI Breakthrough",
            ...     "summary": "Researchers announce...",
            ...     "topics": ["AI", "Research"],
            ...     "url": "https://..."
            ... }
            >>> repo.add_article(article)
            True
        """
        try:
            collection = self.get_collection()

            # Create rich semantic representation
            # Combining title, summary, and topics provides better search context
            # Topics help semantic search understand article themes
            topics_text = ", ".join(article.get("topics", []))
            search_text = f"{article['title']}\n\n{article['summary']}\n\nTopics: {topics_text}"

            # Generate embedding using OpenAI
            embedding = self.generate_embedding(search_text)

            # Prepare metadata (ChromaDB doesn't support nested objects or None values)
            # Metadata enables filtering and rich search results
            metadata = {
                "title": article["title"] or "Untitled",
                "author": article.get("author") or "Unknown",
                "source_domain": article.get("source_domain") or "Unknown",
                "published_date": article.get("published_date") or "",
                "scraped_date": article.get("scraped_date") or "",
                "url": article["url"] or "",
                "topics": topics_text  # Store as comma-separated string
            }

            # Add to ChromaDB collection
            collection.add(
                ids=[str(article["id"])],
                embeddings=[embedding],
                documents=[search_text],  # Store the searchable text
                metadatas=[metadata]
            )

            logger.info(f"Added article {article['id']} to vector database")
            return True

        except Exception as e:
            logger.error(f"Error adding article to vector DB: {str(e)}")
            return False

    def semantic_search(self, query: str, n_results: int = 10) -> List[Dict]:
        """
        Perform semantic search for articles matching the query.

        This is the core semantic search implementation:
        1. Convert query to embedding using OpenAI
        2. Find nearest neighbors in ChromaDB using cosine similarity
        3. Normalize distances to similarity scores [0,1]

        Semantic Search vs Keyword Search:
        - Semantic: "AI breakthrough" matches "machine learning advancement"
        - Keyword: Only matches exact terms
        - This app uses HYBRID search combining both approaches

        Distance to Similarity Conversion:
        ChromaDB returns squared L2 distance [0,2]:
        - 0 = identical vectors
        - 2 = completely different vectors

        Conversion formula: similarity = 1 - (distance / 2)
        - distance 0.0 → similarity 1.0 (100% match)
        - distance 1.0 → similarity 0.5 (50% match)
        - distance 2.0 → similarity 0.0 (0% match)

        Args:
            query: Search query text (e.g., "AI developments in 2024")
            n_results: Number of results to return (default 10)

        Returns:
            List of article dictionaries with:
            - id: Article ID
            - metadata: Article metadata from vector DB
            - distance: Raw ChromaDB distance
            - similarity_score: Normalized similarity [0,1]

        Example:
            >>> repo = VectorRepository()
            >>> results = repo.semantic_search("artificial intelligence", n_results=5)
            >>> for r in results:
            ...     print(f"{r['similarity_score']:.2%} - {r['metadata']['title']}")
            87% - AI Breakthrough in Language Models
            72% - Machine Learning Advances
        """
        try:
            collection = self.get_collection()

            # Generate query embedding using OpenAI
            query_embedding = self.generate_embedding(query)

            # Search in ChromaDB using cosine similarity
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )

            # Format and normalize results
            articles = []
            if results and results["ids"]:
                for i, article_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i]

                    # Convert ChromaDB distance to similarity score
                    # ChromaDB uses squared L2 distance for cosine similarity
                    # Distance range: [0, 2] where 0 = identical, 2 = opposite
                    # Similarity range: [1, 0] where 1 = 100% match, 0 = 0% match
                    similarity_score = max(0, 1 - (distance / 2))

                    articles.append({
                        "id": int(article_id),
                        "metadata": results["metadatas"][0][i],
                        "distance": distance,
                        "similarity_score": similarity_score
                    })

            logger.info(f"Semantic search for '{query}' returned {len(articles)} results")
            return articles

        except Exception as e:
            logger.error(f"Error performing semantic search: {str(e)}")
            return []

    def delete_article(self, article_id: int) -> bool:
        """
        Delete article from vector database.

        Args:
            article_id: Article ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            collection = self.get_collection()
            collection.delete(ids=[str(article_id)])
            logger.info(f"Deleted article {article_id} from vector database")
            return True

        except Exception as e:
            logger.error(f"Error deleting article from vector DB: {str(e)}")
            return False

    def get_stats(self) -> Dict:
        """
        Get statistics about the vector database.

        Returns:
            Dictionary with:
            - count: Number of articles in vector DB
            - collection_name: ChromaDB collection name
            - embedding_model: OpenAI model being used

        Example:
            >>> repo.get_stats()
            {'count': 42, 'collection_name': 'news_articles', 'embedding_model': 'text-embedding-3-small'}
        """
        try:
            collection = self.get_collection()
            count = collection.count()
            return {
                "count": count,
                "collection_name": COLLECTION_NAME,
                "embedding_model": EMBEDDING_MODEL
            }
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {"count": 0, "error": str(e)}

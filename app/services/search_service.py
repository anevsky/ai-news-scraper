"""
Search Service - Hybrid Search Implementation

This module implements sophisticated hybrid search combining AI-powered semantic search
with traditional keyword matching.

GenAI Integration - Hybrid Search Strategy:
1. Semantic Search (AI-powered): OpenAI embeddings + ChromaDB vector similarity
   - Finds conceptually similar articles even with different wording
   - Example: "AI breakthrough" matches "machine learning advancement"

2. Keyword Search (Traditional): SQL LIKE queries across multiple fields
   - Title search: High relevance (90% score)
   - Topic search: Medium-high relevance (85% score)
   - Content search: Medium relevance (70% score)

3. Score Fusion: Combines results, keeps highest score per article
   - Prevents duplicates
   - Prioritizes best match type
   - Enables relevance thresholds

Responsibilities:
- Coordinate semantic and keyword searches
- Deduplicate results with score upgrading
- Apply relevance thresholds
- Sort by similarity score
- Generate search suggestions

Design Pattern: Service Layer
- Orchestrates multiple repositories
- Implements complex business logic
- Provides clean API for routes
"""

import logging
from typing import List, Dict, Tuple

from app.repositories import ArticleRepository, VectorRepository

logger = logging.getLogger(__name__)

# Search configuration
RELEVANCE_THRESHOLD = 0.3  # 30% minimum similarity for main results
SUGGESTION_THRESHOLD = 0.2  # 20% minimum similarity for suggestions


class SearchService:
    """
    Service for hybrid article search combining AI and keyword matching.

    This service implements the "best of both worlds" search strategy:
    - AI semantic search for conceptual matching
    - Keyword search for exact term matching
    - Smart fusion to combine results

    Search Score Priority (Higher score wins):
    1. Title match: 90% (exact keyword in title)
    2. Topic match: 85% (keyword in Claude-identified topics)
    3. Content match: 70% (keyword in summary/content)
    4. Semantic match: Variable 0-100% (AI similarity)

    Example Search Flow:
    Query: "Hardware"
    1. Semantic search finds: "AMD chip deal" (28.9% similarity)
    2. Topic search finds: "AMD chip deal" (has "Hardware" topic)
    3. Deduplication keeps: 85% score (topic match is higher)
    4. Result: Article appears with 85% relevance

    Design Considerations:
    - Score upgrading prevents low semantic scores from hiding good keyword matches
    - Separate main results and suggestions for better UX
    - Limited suggestions (top 5) to avoid clutter
    """

    def __init__(self):
        """Initialize search service with repositories."""
        self.article_repo = ArticleRepository()
        self.vector_repo = VectorRepository()

    def _add_or_upgrade_article(self, articles_by_id: Dict, article: Dict, score: float) -> None:
        """
        Add article to results or upgrade its score if already present.

        Helper method to deduplicate articles and ensure highest score wins.
        This prevents the same article from appearing multiple times with
        different scores from different search tiers.

        Args:
            articles_by_id: Dictionary tracking articles by ID
            article: Article dictionary to add
            score: Similarity score for this search tier

        Example:
            Article found in both semantic (45%) and title (90%) search:
            - First call adds with 45% score
            - Second call upgrades to 90% score (higher)
        """
        article_id = article["id"]
        # Keep highest score if article already found
        if article_id not in articles_by_id or articles_by_id[article_id]["similarity_score"] < score:
            article["similarity_score"] = score
            articles_by_id[article_id] = article

    def search(self, query: str, n_results: int = 15) -> Tuple[List[Dict], List[Dict]]:
        """
        Perform hybrid search combining semantic and keyword methods.

        This is the main search entry point. It implements a sophisticated
        4-tier search strategy:

        Tier 1: Semantic Search (AI-powered)
        - Uses OpenAI embeddings to find conceptually similar articles
        - Searches analyzed articles with embeddings in ChromaDB
        - Variable relevance (0-100% based on vector similarity)

        Tier 2: Title Search (Keyword)
        - SQL ILIKE search in article titles
        - 90% relevance score (highly relevant if in title)
        - Searches all articles (including non-analyzed)

        Tier 3: Topic Search (Keyword + AI)
        - Searches Claude-identified topics
        - 85% relevance score (very relevant if matches theme)
        - Leverages AI topic extraction

        Tier 4: Content Search (Keyword)
        - Searches summary and full content
        - 70% relevance score (relevant but may be tangential)

        Score Fusion Logic:
        - Results deduplicated by article ID
        - Highest score wins for each article
        - Prevents semantic search from "hiding" better keyword matches

        Args:
            query: User search query (e.g., "AI developments")
            n_results: Maximum semantic search results (default 15)

        Returns:
            Tuple of (main_results, suggestions):
            - main_results: Articles >= 30% relevance (sorted by score)
            - suggestions: Articles 20-30% relevance (top 5, sorted by score)

        Example:
            >>> service = SearchService()
            >>> main, suggestions = service.search("artificial intelligence")
            >>> for article in main:
            ...     print(f"{article['similarity_score']:.0%} - {article['title']}")
            90% - AI Breakthrough in Language Models (title match)
            85% - Machine Learning Advances (topic match)
            72% - Tech Industry Updates (content match)
            45% - Future of Computing (semantic match)
        """
        logger.info(f"Performing hybrid search for: {query}")

        # Dictionary to track articles by ID and keep highest score
        # This prevents duplicates and ensures best match type wins
        articles_by_id = {}

        # Tier 1: Semantic Search (AI-powered with OpenAI embeddings)
        # Only searches analyzed articles that have embeddings in ChromaDB
        semantic_results = self.vector_repo.semantic_search(query, n_results=n_results)
        for result in semantic_results:
            article = self.article_repo.get_by_id(result["id"])
            if article:
                # Normalize score to [0,1] range
                score = result.get("similarity_score", 0)
                article["similarity_score"] = max(0, min(1, score))
                articles_by_id[article["id"]] = article

        # Tier 2: Title Search (Keyword matching)
        # High relevance - if query appears in title, very likely relevant
        title_results = self.article_repo.search_by_title(query)
        for article in title_results:
            self._add_or_upgrade_article(articles_by_id, article, score=0.9)

        # Tier 3: Topic Search (Keyword in Claude-identified topics)
        # Very relevant - if query matches a main theme
        topic_results = self.article_repo.search_by_topic(query)
        for article in topic_results:
            self._add_or_upgrade_article(articles_by_id, article, score=0.85)

        # Tier 4: Content Search (Keyword in summary/content)
        # Medium relevance - query mentioned but may not be main topic
        content_results = self.article_repo.search_by_content(query)
        for article in content_results:
            self._add_or_upgrade_article(articles_by_id, article, score=0.7)

        # Convert dict to list for sorting
        all_results = list(articles_by_id.values())

        # Split results into main and suggestions based on relevance thresholds
        # Main: >= 30% relevance (confident matches)
        main_results = sorted(
            [r for r in all_results if r["similarity_score"] >= RELEVANCE_THRESHOLD],
            key=lambda x: x["similarity_score"],
            reverse=True
        )

        # Suggestions: 20-30% relevance (possible matches)
        suggestion_results = sorted(
            [r for r in all_results if SUGGESTION_THRESHOLD <= r["similarity_score"] < RELEVANCE_THRESHOLD],
            key=lambda x: x["similarity_score"],
            reverse=True
        )[:5]  # Limit to top 5 suggestions

        logger.info(
            f"Search '{query}' found {len(main_results)} relevant and "
            f"{len(suggestion_results)} suggested results"
        )

        return main_results, suggestion_results

    def get_stats(self) -> Dict:
        """
        Get search system statistics.

        Returns:
            Dictionary with:
            - total_articles: Total articles in database
            - indexed_articles: Articles with embeddings (searchable)
            - collection_name: ChromaDB collection name
            - embedding_model: OpenAI model being used

        Example:
            >>> stats = service.get_stats()
            >>> print(f"{stats['indexed_articles']}/{stats['total_articles']} articles searchable")
        """
        all_articles = self.article_repo.get_all()
        vector_stats = self.vector_repo.get_stats()

        return {
            "total_articles": len(all_articles),
            "indexed_articles": vector_stats.get("count", 0),
            "collection_name": vector_stats.get("collection_name"),
            "embedding_model": vector_stats.get("embedding_model")
        }

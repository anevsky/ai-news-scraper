"""
Search Routes - Hybrid Search Endpoints

This module handles search-related HTTP endpoints using the hybrid search service.

GenAI Features:
- Semantic search with OpenAI embeddings
- Keyword search across multiple fields
- Intelligent result fusion and ranking

Design Pattern: Controller/Router Layer
- Handles HTTP request/response
- Delegates to SearchService
- Returns HTML templates with search results
"""

import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services import SearchService

logger = logging.getLogger(__name__)

# Initialize router and templates
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, query: str):
    """
    Display search results page with hybrid search.

    This endpoint implements the user-facing search interface, combining:
    1. AI-powered semantic search (OpenAI embeddings + ChromaDB)
    2. Keyword search across title, topics, and content
    3. Smart result fusion with score upgrading
    4. Relevance-based filtering

    Search Flow:
    1. User enters query (e.g., "artificial intelligence")
    2. SearchService performs 4-tier hybrid search:
       - Semantic: Finds conceptually similar articles
       - Title: Finds exact matches in titles (90% score)
       - Topic: Finds matches in Claude-identified topics (85% score)
       - Content: Finds matches in summaries/content (70% score)
    3. Results deduplicated with highest score kept
    4. Split into main results (≥30%) and suggestions (20-30%)
    5. Rendered in HTML template

    Args:
        request: FastAPI request object
        query: Search query string

    Returns:
        HTML template with:
        - query: Original search query
        - results: Main results (≥30% relevance)
        - suggestions: Related articles (20-30% relevance)

    Example:
        GET /search?query=Hardware
        Returns articles with "Hardware" in title/topics/content
        or semantically similar to "Hardware"
    """
    logger.info(f"Search query: {query}")

    try:
        search_service = SearchService()

        # Perform hybrid search
        main_results, suggestions = search_service.search(query, n_results=15)

        logger.info(
            f"Found {len(main_results)} relevant and {len(suggestions)} "
            f"suggested results for query: {query}"
        )

        return templates.TemplateResponse("search_results.html", {
            "request": request,
            "query": query,
            "results": main_results,
            "suggestions": suggestions
        })

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        # Return empty results instead of error to maintain UX
        return templates.TemplateResponse("search_results.html", {
            "request": request,
            "query": query,
            "results": [],
            "suggestions": [],
            "error": str(e)
        })


@router.post("/api/search")
async def search_api(query: str = Form(...)):
    """
    API endpoint for search (kept for backward compatibility).

    Returns redirect URL to search results page.

    Args:
        query: Search query string

    Returns:
        JSON with redirect URL
    """
    return {
        "redirect": f"/search?query={query}"
    }


@router.get("/api/search/stats")
async def search_stats():
    """
    Get search system statistics.

    Returns:
        JSON with:
        - total_articles: Total articles in database
        - indexed_articles: Articles with embeddings (searchable via semantic search)
        - collection_name: ChromaDB collection name
        - embedding_model: OpenAI model being used

    Example Response:
        {
            "total_articles": 42,
            "indexed_articles": 38,
            "collection_name": "news_articles",
            "embedding_model": "text-embedding-3-small"
        }
    """
    try:
        search_service = SearchService()
        stats = search_service.get_stats()
        return stats

    except Exception as e:
        logger.error(f"Error getting search stats: {str(e)}")
        return {
            "error": str(e),
            "total_articles": 0,
            "indexed_articles": 0
        }

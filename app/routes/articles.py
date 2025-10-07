"""
Article Routes - CRUD Operations

This module handles HTTP endpoints for article management:
- List all articles
- Get single article by ID
- Delete article(s)
- Scrape new article
- Analyze article with Claude AI

Design Pattern: Controller/Router Layer
- Handles HTTP request/response
- Validates input
- Delegates to service layer
- Returns JSON or HTML templates
"""

import logging
from fastapi import APIRouter, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import List

from app.services import ScraperService, AnalyzerService, ChatService
from app.repositories import ArticleRepository, VectorRepository

logger = logging.getLogger(__name__)

# Initialize router and templates
router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ===== View Endpoints (HTML) =====

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Render the main page with article scraping interface and history.

    This is the primary user interface showing:
    - Scraping form for new articles
    - List of all scraped/analyzed articles
    - Quick actions (analyze, delete)

    Returns:
        HTML template with article list
    """
    article_repo = ArticleRepository()
    articles = article_repo.get_all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "articles": articles
    })


@router.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int):
    """
    View detailed page for a specific article.

    Shows:
    - Full article content (if analyzed)
    - Summary and topics
    - Metadata (author, date, source)
    - Performance metrics

    Args:
        request: FastAPI request object
        article_id: Article ID to display

    Returns:
        HTML template with article details

    Raises:
        HTTPException: 404 if article not found
    """
    article_repo = ArticleRepository()
    article = article_repo.get_by_id(article_id)

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # If not analyzed yet, show message
    if not article.get("has_analysis"):
        article["content"] = "Article has not been analyzed yet. Click 'Analyze' to extract content."

    return templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article,
        "article_id": article_id
    })


# ===== API Endpoints (JSON) =====

@router.get("/api/articles")
async def list_articles():
    """
    API endpoint to get list of all scraped articles with metadata.

    Returns:
        JSON with articles array (without full content for performance)
    """
    article_repo = ArticleRepository()
    articles = article_repo.get_all()
    return {"articles": articles}


@router.get("/api/article/{article_id}")
async def get_article(article_id: int):
    """
    API endpoint to get a single article by ID.

    Args:
        article_id: Article ID

    Returns:
        JSON with full article data including content

    Raises:
        HTTPException: 404 if article not found
    """
    article_repo = ArticleRepository()
    article = article_repo.get_by_id(article_id)

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return {"article": article}


@router.post("/scrape")
async def scrape_article(url: str = Form(...)):
    """
    Download and save raw HTML from a news article URL.

    This endpoint implements the first stage of article processing:
    1. Download HTML with browser-like headers (anti-bot)
    2. Extract basic title from HTML meta tags
    3. Save HTML file to disk
    4. Save metadata to database

    The article is NOT analyzed yet - analysis happens separately via /analyze endpoint.
    This separation allows users to scrape multiple articles quickly, then analyze later.

    Args:
        url: The URL of the news article to scrape

    Returns:
        JSON with:
        - status: 'success' or 'duplicate'
        - filename: Saved HTML filename
        - url: Article URL
        - html_size: Downloaded HTML size
        - article_id: Database ID
        - message: Status message (for duplicates)

    Raises:
        HTTPException: 400 if download fails, 500 if database save fails
    """
    try:
        scraper = ScraperService()
        result = scraper.scrape_article(url)
        return result

    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analyze/{article_id}")
async def analyze_article(article_id: int, background_tasks: BackgroundTasks):
    """
    Analyze a previously downloaded article using Claude AI in the background.

    This endpoint implements the second stage of article processing:
    1. Checks if article exists and has HTML file
    2. Starts Claude analysis in background task
    3. Returns immediately (non-blocking)

    Background analysis flow:
    1. Read HTML from disk
    2. Send to Claude for extraction
    3. Save results to database
    4. Add to vector store for semantic search

    This non-blocking approach allows users to:
    - Continue using the app while analysis runs
    - Analyze multiple articles in parallel
    - Not wait for slow API calls

    Args:
        article_id: Article ID to analyze
        background_tasks: FastAPI background tasks handler

    Returns:
        JSON with:
        - status: 'analyzing' or 'already_analyzed'
        - message: Status description
        - article_id: Database ID
        - url: Article URL

    Raises:
        HTTPException: 404 if article or HTML file not found

    Example Response:
        {
            "status": "analyzing",
            "message": "Analysis started in background",
            "article_id": 123,
            "url": "https://example.com/article"
        }
    """
    article_repo = ArticleRepository()
    db_article = article_repo.get_by_id(article_id)

    if not db_article:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found in database")

    # Check if already analyzed
    if db_article.get("has_analysis"):
        return {
            "status": "already_analyzed",
            "message": "Article has already been analyzed",
            "article_id": article_id
        }

    html_path = Path(db_article["raw_html_path"])

    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"HTML file not found: {html_path}")

    url = db_article["url"]

    # Add analysis task to background
    # FastAPI's BackgroundTasks runs sync functions in thread pool automatically
    analyzer = AnalyzerService()
    background_tasks.add_task(
        analyzer.analyze_article,
        article_id,
        html_path,
        url
    )

    logger.info(f"Analysis task queued for article ID {article_id}: {url}")

    return {
        "status": "analyzing",
        "message": "Analysis started in background",
        "article_id": article_id,
        "url": url
    }


@router.post("/analyze/batch")
async def analyze_batch(article_ids: List[int] = Form(...)):
    """
    Analyze multiple articles in parallel using Claude AI.

    This endpoint enables bulk analysis for faster processing:
    - Downloads run concurrently (not sequentially)
    - All Claude API calls run in parallel
    - Results aggregated at the end

    Use case: User scrapes 10 articles, then clicks "Analyze All"

    Args:
        article_ids: List of article IDs to analyze

    Returns:
        JSON with:
        - status: 'complete'
        - total: Number of articles requested
        - successes: Number successfully analyzed
        - failures: Number that failed
        - total_duration_ms: Total time for all analyses
        - total_tokens: Total Claude API tokens used
        - results: Array of individual results

    Example Response:
        {
            "status": "complete",
            "total": 5,
            "successes": 4,
            "failures": 1,
            "total_duration_ms": 12500,
            "total_tokens": 18000,
            "results": [...]
        }
    """
    import asyncio

    logger.info(f"Starting batch analysis of {len(article_ids)} articles")

    article_repo = ArticleRepository()
    analyzer = AnalyzerService()

    async def analyze_single(article_id: int):
        """Analyze a single article and return result."""
        try:
            # Get article from database
            db_article = article_repo.get_by_id(article_id)
            if not db_article:
                return {"article_id": article_id, "status": "error", "error": "Article not found"}

            html_path = Path(db_article["raw_html_path"])
            if not html_path.exists():
                return {"article_id": article_id, "status": "error", "error": "HTML file not found"}

            url = db_article["url"]

            # Analyze with Claude
            result = analyzer.analyze_article(article_id, html_path, url)

            return result

        except Exception as e:
            logger.error(f"Failed to analyze article {article_id}: {str(e)}")
            return {"article_id": article_id, "status": "error", "error": str(e)}

    # Run all analyses in parallel
    results = await asyncio.gather(*[analyze_single(aid) for aid in article_ids])

    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "error"]

    total_duration = sum(r.get("duration_ms", 0) for r in successes)
    total_tokens = sum(r.get("tokens_used", 0) for r in successes)

    logger.info(f"Batch analysis complete: {len(successes)} succeeded, {len(failures)} failed")

    return {
        "status": "complete",
        "total": len(article_ids),
        "successes": len(successes),
        "failures": len(failures),
        "total_duration_ms": total_duration,
        "total_tokens": total_tokens,
        "results": results
    }


@router.delete("/api/article/{article_id}")
async def delete_article(article_id: int):
    """
    Delete a single article by ID.

    Cleanup steps:
    1. Delete from vector database (ChromaDB)
    2. Delete from SQLite database
    3. Delete HTML file from disk

    Args:
        article_id: Article ID to delete

    Returns:
        JSON with success status

    Raises:
        HTTPException: 404 if article not found
    """
    vector_repo = VectorRepository()
    article_repo = ArticleRepository()

    # Delete from vector database first
    vector_repo.delete_article(article_id)

    # Delete from SQLite database and cleanup HTML file
    success = article_repo.delete(article_id)

    if not success:
        raise HTTPException(status_code=404, detail="Article not found")

    logger.info(f"Deleted article {article_id}")
    return {"status": "success", "message": f"Article {article_id} deleted"}


@router.delete("/api/articles")
async def delete_all_articles():
    """
    Delete all articles from database and vector store.

    Cleanup steps:
    1. Delete all from vector database (ChromaDB)
    2. Delete all from SQLite database
    3. Delete all HTML files from disk

    Returns:
        JSON with success status

    Raises:
        HTTPException: 500 if deletion fails
    """
    vector_repo = VectorRepository()
    article_repo = ArticleRepository()

    # Get all articles first
    articles = article_repo.get_all()

    # Delete from vector database
    for article in articles:
        try:
            vector_repo.delete_article(article["id"])
        except Exception as e:
            logger.warning(f"Could not delete article {article['id']} from vector DB: {str(e)}")

    # Delete all from SQLite database and cleanup HTML files
    success = article_repo.delete_all()

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete articles")

    logger.info("Deleted all articles")
    return {"status": "success", "message": "All articles deleted"}


@router.post("/api/chat/{article_id}")
async def chat_about_article(
    article_id: int,
    message: str = Form(...),
    history: str = Form(default="[]")
):
    """
    Chat with Claude AI about an article.

    Allows users to ask questions about analyzed articles and get
    intelligent responses based on the article content.

    Args:
        article_id: ID of the article to discuss
        message: User's question or message
        history: JSON string of conversation history (optional)
            Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    Returns:
        JSON with:
        - response: Claude's answer
        - tokens: Number of tokens used
        - input_tokens: Input tokens
        - output_tokens: Output tokens

    Raises:
        HTTPException: 404 if article not found
        HTTPException: 400 if article not analyzed
        HTTPException: 500 if chat fails

    Example Request:
        POST /api/chat/123
        message=What is the main topic?
        history=[]

    Example Response:
        {
            "response": "The main topic is...",
            "tokens": 150,
            "input_tokens": 100,
            "output_tokens": 50
        }
    """
    import json as json_module

    # Parse conversation history
    try:
        conversation_history = json_module.loads(history)
    except json_module.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid conversation history format")

    # Initialize chat service
    chat_service = ChatService()

    try:
        # Get chat response
        result = chat_service.chat(
            article_id=article_id,
            user_message=message,
            conversation_history=conversation_history
        )

        logger.info(f"Chat response for article {article_id}: {result['tokens']} tokens")

        return result

    except ValueError as e:
        # Article not found or not analyzed
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Chat error for article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

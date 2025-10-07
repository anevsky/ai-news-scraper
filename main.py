"""
News Scraper Application - Main Entry Point

A sophisticated web application for scraping, analyzing, and searching news articles
using state-of-the-art GenAI technologies.

GenAI Technology Stack:
1. Anthropic Claude Sonnet 4.5 - Article content extraction and analysis
   - Extracts clean article text from HTML
   - Generates concise summaries
   - Identifies main topics and themes

2. OpenAI text-embedding-3-small - Semantic search embeddings
   - Converts articles to 1536-dimensional vectors
   - Enables conceptual similarity matching

3. ChromaDB - Vector database for semantic search
   - Stores article embeddings
   - Performs fast cosine similarity search

Architecture:
- FastAPI: Async web framework
- SQLAlchemy ORM: Structured data (metadata, content)
- ChromaDB: Vector data (embeddings)
- DaisyUI + TailwindCSS: Modern UI

Key Features:
- Web scraping with anti-bot protection
- AI-powered content extraction (Claude)
- Hybrid search (semantic + keyword)
- Background task processing
- Performance metrics tracking

Design Patterns:
- Repository Pattern: Data access abstraction
- Service Layer: Business logic encapsulation
- Controller/Router: HTTP handling
- Dependency Injection: Loose coupling
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging
from pathlib import Path
from dotenv import load_dotenv

from app.routes import articles_router, search_router
from app.repositories import ArticleRepository

# Load environment variables from .env file
load_dotenv()

# Configure comprehensive logging
# Logs both to file and console for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="News Scraper with AI Analysis",
    description=(
        "Web application for scraping and analyzing news articles using "
        "Anthropic Claude for content extraction and OpenAI for semantic search"
    ),
    version="2.0.0"
)

# Mount static files (CSS, JavaScript, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware for API access from different origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers for different feature areas
# This modular approach separates concerns and improves maintainability
app.include_router(articles_router, tags=["articles"])
app.include_router(search_router, tags=["search"])


@app.on_event("startup")
async def startup_event():
    """
    Application startup initialization.

    Performs one-time setup:
    1. Initialize database tables (SQLAlchemy)
    2. Create required directories
    3. Log startup information

    This ensures the application is ready to handle requests.
    """
    logger.info("Starting News Scraper application...")

    # Initialize database tables
    article_repo = ArticleRepository()
    article_repo.initialize_database()
    logger.info("Database initialized")

    # Create required directories
    Path("downloaded_html").mkdir(exist_ok=True)
    logger.info("Created required directories")

    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown cleanup.

    Performs graceful shutdown:
    - Log shutdown event
    - Close any open connections (handled by repositories)
    """
    logger.info("Shutting down News Scraper application...")


# Health check endpoint for monitoring
@app.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        JSON with status and basic system info
    """
    return {
        "status": "healthy",
        "app": "News Scraper",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn

    # Run application with uvicorn ASGI server
    # Use --reload in development for auto-restart on code changes
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

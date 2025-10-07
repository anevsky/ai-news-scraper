# Architecture Documentation

## Overview

This document describes the professional architecture refactoring of the News Scraper application, transforming it from a monolithic structure to a well-organized, maintainable codebase following industry best practices.

## Refactoring Goals

1. **Single Responsibility Principle**: Each module has one clear purpose
2. **Separation of Concerns**: Clear boundaries between layers
3. **Code Documentation**: Comprehensive comments highlighting GenAI usage
4. **Maintainability**: Easy to understand, test, and extend

## Architecture Layers

### 1. Models Layer (`app/models/`)

**Purpose**: Define database schema and ORM models

**Files**:
- `article.py`: Article model with full lifecycle tracking

**Responsibilities**:
- SQLAlchemy ORM model definition
- Database schema (columns, indexes, constraints)
- Model-to-dict conversion for API responses
- Computed properties (e.g., `has_analysis`)

**Key Features**:
- Comprehensive field documentation
- ISO timestamp handling
- JSON field parsing (topics, validation warnings)
- Performance metric storage (tokens, duration)

### 2. Repository Layer (`app/repositories/`)

**Purpose**: Abstract data access and persistence

**Files**:
- `article_repository.py`: SQL database operations
- `vector_repository.py`: Vector database operations (ChromaDB)

**Design Pattern**: Repository Pattern
- Hides implementation details from business logic
- Provides clean, testable interface
- Easy to mock for unit tests
- Enables database migration if needed

**ArticleRepository**:
```python
# CRUD operations
save_article(url, html_path, title) -> article_id
update_article_analysis(url, data, duration, tokens) -> success
get_by_id(article_id) -> article_dict
get_by_url(url) -> article_dict
get_all(limit) -> articles_list
delete(article_id) -> success

# Search operations
search_by_title(query) -> articles
search_by_topic(query) -> articles
search_by_content(query) -> articles
```

**VectorRepository**:
```python
# Embedding operations
generate_embedding(text) -> vector[1536]
add_article(article) -> success

# Search operations
semantic_search(query, n_results) -> results_with_scores

# Management
delete_article(article_id) -> success
get_stats() -> stats_dict
```

**GenAI Integration**:
- OpenAI API for embeddings (lazy initialization)
- ChromaDB for vector storage
- Rich embeddings (title + summary + topics)
- Distance-to-similarity conversion

### 3. Service Layer (`app/services/`)

**Purpose**: Implement business logic and orchestrate operations

**Files**:
- `scraper_service.py`: Web scraping logic
- `analyzer_service.py`: Claude AI analysis
- `search_service.py`: Hybrid search orchestration

**Design Pattern**: Service Layer
- Encapsulates complex business logic
- Coordinates multiple repositories
- Integrates external APIs (Claude, OpenAI)
- Provides transaction-like operations

**ScraperService**:
```python
scrape_article(url) -> result_dict
# - Duplicate detection
# - HTTP download with anti-bot headers
# - Basic title extraction (regex)
# - HTML file storage
# - Database persistence
```

**AnalyzerService**:
```python
analyze_article(article_id, html_path, url) -> result_dict
# - Claude AI content extraction
# - Smart HTML truncation
# - Structured JSON parsing
# - Content quality validation
# - Performance metrics tracking
# - Database update
# - Vector store indexing
```

**SearchService**:
```python
search(query, n_results) -> (main_results, suggestions)
# - 4-tier hybrid search:
#   1. Semantic (OpenAI embeddings)
#   2. Title match (90% score)
#   3. Topic match (85% score)
#   4. Content match (70% score)
# - Result deduplication
# - Score upgrading (keep highest)
# - Relevance threshold filtering
```

**GenAI Integration**:
- **Claude Sonnet 4.5**: Article analysis
  - HTML to clean text extraction
  - Summary generation
  - Topic identification
  - Metadata extraction

- **OpenAI text-embedding-3-small**: Semantic search
  - 1536-dimensional vectors
  - Cosine similarity matching
  - ~$0.02 per 1M tokens

### 4. Routes Layer (`app/routes/`)

**Purpose**: Handle HTTP requests and responses

**Files**:
- `articles.py`: Article CRUD endpoints
- `search.py`: Search endpoints

**Design Pattern**: Controller/Router
- Thin layer delegating to services
- Request validation
- Response formatting
- HTTP error handling

**Endpoints**:

Articles:
```python
GET  /                    # Home page
POST /scrape              # Scrape article
POST /analyze/{id}        # Analyze with Claude (background)
GET  /article/{id}        # Article details
GET  /api/articles        # List articles (JSON)
DELETE /api/article/{id}  # Delete article
DELETE /api/articles      # Delete all
```

Search:
```python
GET /search?query=...     # Search results page
GET /api/search/stats     # Search statistics
```

### 5. Main Application (`main.py`)

**Purpose**: Application entry point and configuration

**Responsibilities**:
- FastAPI app initialization
- Router registration
- Middleware configuration (CORS)
- Startup/shutdown events
- Static file serving

**Startup Flow**:
1. Load environment variables
2. Configure logging
3. Initialize FastAPI app
4. Mount static files
5. Register routers
6. Initialize database on startup

## Data Flow

```
HTTP Request
    ↓
Routes (Controller)
    ↓
Services (Business Logic)
    ↓
Repositories (Data Access)
    ↓
[Database / Vector Store / GenAI APIs]
```

### Example: Article Analysis Flow

```
1. POST /analyze/{id}
   ↓
2. articles.py: analyze_article()
   - Validate article exists
   - Queue background task
   ↓
3. analyzer_service.py: analyze_article()
   - Read HTML file
   - Call _analyze_with_claude()
   - Track performance metrics
   ↓
4. Claude API
   - Extract content from HTML
   - Generate summary
   - Identify topics
   ↓
5. article_repository.py: update_article_analysis()
   - Save to SQLite database
   ↓
6. vector_repository.py: add_article()
   - Generate OpenAI embedding
   - Store in ChromaDB
   ↓
7. Return success response
```

### Example: Hybrid Search Flow

```
1. GET /search?query=Hardware
   ↓
2. search.py: search_page()
   - Extract query parameter
   ↓
3. search_service.py: search()
   - Semantic search (OpenAI + ChromaDB): 28.9% match
   - Title search (SQL LIKE): No match
   - Topic search (SQL LIKE): 85% match ✓ (highest)
   - Content search (SQL LIKE): No match
   - Deduplicate: Keep 85% score
   - Filter: >= 30% threshold
   - Sort: By score descending
   ↓
4. Render search_results.html
   - Main results: Articles >= 30%
   - Suggestions: Articles 20-30%
```

## Backward Compatibility

To maintain compatibility with existing tests and code:

**Compatibility Wrappers**:
- `models.py` → `app/models/article.py`
- `database.py` → `app/repositories/article_repository.py`
- `vector_store.py` → `app/repositories/vector_repository.py`

**Implementation**:
```python
# database.py (compatibility wrapper)
from app.repositories import ArticleRepository
from app.models import get_session

_repo = ArticleRepository()

def get_all_articles(limit=100):
    """Backward compatible wrapper."""
    return _repo.get_all(limit)
```

This allows gradual migration without breaking existing code.

## Code Quality Features

### 1. Comprehensive Documentation

**Module-Level**:
- Clear purpose statement
- Responsibilities list
- GenAI integration details
- Design pattern explanation

**Function-Level**:
- Detailed docstrings
- Parameter descriptions
- Return value documentation
- Usage examples
- GenAI usage highlighting

**Example**:
```python
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
```

### 2. Code Comments

**Strategic Comments**:
- Explain WHY, not WHAT
- Document design decisions
- Highlight GenAI integration points
- Clarify complex algorithms

**Example**:
```python
# Smart HTML truncation - locate article content section
# This reduces token usage by ~50% while ensuring complete article extraction
article_start = max(
    html_content.find('<article'),
    html_content.find('class="article'),
    html_content.find('class="post-content'),
    html_content.find('class="entry-content'),
    html_content.find('<main')
)
```

### 3. Type Hints

```python
def search(self, query: str, n_results: int = 15) -> Tuple[List[Dict], List[Dict]]:
    """Return (main_results, suggestions)."""
```

### 4. Error Handling

```python
try:
    article_data, tokens_used = self._analyze_with_claude(raw_html, url)
except json.JSONDecodeError as e:
    # Save failed response for debugging
    error_file = Path("downloaded_html") / f"error_{datetime.now()}.txt"
    with open(error_file, "w") as f:
        f.write(f"Error: {e}\n{response_text}")
    raise Exception(f"Failed to parse Claude response. Saved to {error_file}")
```

### 5. Logging

```python
logger.info(f"Starting analysis of article ID {article_id}: {url}")
logger.warning(f"Content validation issues: {', '.join(warnings)}")
logger.error(f"Claude API error: {str(e)}")
```

## Testing Strategy

**Test Organization**:
- `tests/test_database.py`: Repository layer tests
- `tests/test_vector_store.py`: Vector operations tests
- `tests/test_search.py`: Hybrid search tests

**Test Coverage**:
- Unit tests for each repository method
- Integration tests for search flow
- Mock-based tests for external APIs

## Deployment Considerations

### Environment Variables

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional
ANTHROPIC_LLM_MODEL=claude-sonnet-4-5-20250929
EMBEDDING_MODEL=text-embedding-3-small
COLLECTION_NAME=news_articles
```

### Directory Structure

```
news-scraper/
├── app/              # Application code
├── downloaded_html/  # Article HTML files
├── chroma_db/       # Vector database
├── news_scraper.db  # SQLite database
└── news_scraper.log # Application logs
```

### Health Monitoring

```bash
curl http://localhost:8000/health
# {"status": "healthy", "app": "News Scraper", "version": "2.0.0"}
```

## Performance Optimizations

1. **HTML Truncation**: Reduces Claude API token usage by ~50%
2. **Background Tasks**: Non-blocking analysis for better UX
3. **Lazy Initialization**: Deferred API client creation
4. **Batch Operations**: Parallel article analysis
5. **Database Indexes**: URL, source_domain, scraped_date
6. **Score Caching**: Results deduplicated before sorting

## Security Considerations

1. **API Key Protection**: Environment variables, not in code
2. **SQL Injection**: Parameterized queries via SQLAlchemy
3. **Path Traversal**: Absolute paths, no user input in file paths
4. **CORS**: Configured for specific origins in production

## Future Enhancements

Potential improvements while maintaining architecture:

1. **Caching Layer**: Redis for search results
2. **Queue System**: Celery for background tasks
3. **Rate Limiting**: Prevent API abuse
4. **User Authentication**: Multi-user support
5. **Advanced Analytics**: Article trends, topic clustering
6. **Export Features**: PDF, CSV, JSON exports
7. **Webhooks**: Notify on analysis completion

## Conclusion

This architecture provides:
- ✅ Clear separation of concerns
- ✅ Maintainable, testable code
- ✅ Well-documented GenAI integration
- ✅ Professional code organization
- ✅ Scalable foundation for growth

The refactoring transforms a working prototype into production-ready code suitable for:
- Job portfolio demonstration
- Open source publication
- Team collaboration
- Future enhancement

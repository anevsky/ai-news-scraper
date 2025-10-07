"""
Analyzer Service - AI-Powered Article Analysis

This module uses Claude AI to extract and analyze article content from HTML.

GenAI Integration - Anthropic Claude:
- Model: claude-sonnet-4-5-20250929
- Task: Extract clean article text from noisy HTML
- Capabilities:
  * Remove ads, navigation, and other non-content elements
  * Generate concise 2-3 sentence summaries
  * Identify main topics and themes
  * Extract metadata (title, author, publication date)

Responsibilities:
- Analyze HTML with Claude AI
- Extract clean content, summary, and topics
- Validate extraction quality
- Track performance metrics (tokens, duration)
- Save analyzed data to database and vector store

Design Pattern: Service Layer
- Encapsulates complex AI analysis logic
- Coordinates between Claude API, database, and vector store
- Provides robust error handling for AI operations
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict
from anthropic import Anthropic

from app.repositories import ArticleRepository, VectorRepository

logger = logging.getLogger(__name__)

# Claude AI configuration
# 200KB provides enough content for most long-form articles while staying within token limits
MAX_HTML_LENGTH = 200_000  # ~50K tokens (Claude Sonnet 4.5 supports 200K input tokens)

# Maximum tokens for Claude response (covers extracted article + summary + metadata)
# Increased to handle long-form articles (typical article is 1-3K tokens of content)
MAX_RESPONSE_TOKENS = 8_000


class AnalyzerService:
    """
    Service for AI-powered article analysis using Claude.

    This service implements the second stage of article processing:
    extracting clean content and generating insights from raw HTML.

    GenAI Technology: Anthropic Claude Sonnet 4.5
    - Purpose: Extract structured data from unstructured HTML
    - Model: claude-sonnet-4-5-20250929
    - Input: Raw HTML (up to 200KB)
    - Output: Structured JSON with title, content, summary, topics
    - Performance: ~2-5 seconds per article, 2-8K tokens

    Key Features:
    1. Intelligent HTML Parsing: Locates article content, skips ads/nav
    2. Content Extraction: Removes HTML tags, keeps clean text
    3. Summarization: Generates 2-3 sentence summaries
    4. Topic Identification: Extracts main themes and keywords
    5. Metadata Extraction: Finds author, publication date

    Design Considerations:
    - HTML truncation strategy (find <article> tag)
    - JSON parsing with error recovery
    - Content validation and quality checks
    - Performance tracking (tokens, duration)
    - Background task support for async processing
    """

    def __init__(self):
        """Initialize analyzer service with Claude client and repositories."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.claude_client = Anthropic(api_key=api_key)
        self.article_repo = ArticleRepository()
        self.vector_repo = VectorRepository()

    def analyze_article(self, article_id: int, html_path: Path, url: str) -> Dict:
        """
        Analyze article with Claude AI and save results.

        This is the main entry point for article analysis. It:
        1. Reads raw HTML from disk
        2. Sends to Claude for extraction
        3. Validates extracted content
        4. Saves to database
        5. Adds to vector store for semantic search
        6. Tracks performance metrics

        Args:
            article_id: Database ID of article
            html_path: Path to saved HTML file
            url: Original article URL

        Returns:
            Dictionary with:
            - status: 'success' or 'error'
            - article_id: Database ID
            - duration_ms: Analysis duration in milliseconds
            - tokens_used: Total Claude API tokens
            - error: Error message (if failed)

        Example:
            >>> service = AnalyzerService()
            >>> result = service.analyze_article(
            ...     123,
            ...     Path("downloaded_html/20250107_123456.html"),
            ...     "https://example.com/article"
            ... )
            >>> print(f"Analyzed in {result['duration_ms']}ms using {result['tokens_used']} tokens")
        """
        try:
            logger.info(f"Starting analysis of article ID {article_id}: {url}")

            # Read the raw HTML content
            with open(html_path, "r", encoding="utf-8") as f:
                raw_html = f.read()

            # Track analysis time for performance metrics
            start_time = time.time()

            # Use Claude to extract and analyze article content
            article_data, tokens_used = self._analyze_with_claude(raw_html, url)

            # Calculate duration in milliseconds
            duration_ms = int((time.time() - start_time) * 1000)

            # Generate JSON filename based on HTML filename (backward compatibility)
            timestamp = html_path.stem  # Gets filename without extension
            json_filename = f"{timestamp}_article.json"
            json_filepath = Path("downloaded_html") / json_filename

            # Add metadata to article data
            article_data["raw_html_file"] = str(html_path.name)
            article_data["extracted_at"] = datetime.now().isoformat()
            article_data["analysis_duration_ms"] = duration_ms
            article_data["analysis_tokens"] = tokens_used

            # Save structured article data as JSON (for backward compatibility)
            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(article_data, f, indent=2, ensure_ascii=False)

            # Update database with Claude analysis results and performance metrics
            self.article_repo.update_article_analysis(url, article_data, duration_ms, tokens_used)

            # Add to vector database for semantic search
            # Only analyzed articles with clean content can be searched semantically
            db_article_updated = self.article_repo.get_by_url(url)
            if db_article_updated:
                self.vector_repo.add_article(db_article_updated)
                logger.info(f"Added article {article_id} to vector database")

            logger.info(f"Analysis complete for article ID {article_id}. Duration: {duration_ms}ms, Tokens: {tokens_used}")

            return {
                "status": "success",
                "article_id": article_id,
                "duration_ms": duration_ms,
                "tokens_used": tokens_used
            }

        except Exception as e:
            logger.error(f"Analysis failed for article ID {article_id}: {str(e)}")
            return {
                "status": "error",
                "article_id": article_id,
                "error": str(e)
            }

    def _analyze_with_claude(self, html_content: str, url: str) -> Tuple[Dict, int]:
        """
        Extract and analyze article content from HTML using Claude AI.

        This is the core GenAI integration - using Claude's advanced language
        understanding to:
        1. Identify article content among HTML noise (ads, navigation, etc.)
        2. Extract clean text without HTML tags
        3. Generate concise summary
        4. Identify main topics and themes
        5. Find metadata (author, date)

        GenAI Strategy - Smart HTML Truncation:
        To minimize token usage while ensuring complete article extraction:
        1. Search for <article>, <main>, or article-related class names
        2. Extract from that point forward (skips header/nav)
        3. Truncate at MAX_HTML_LENGTH (200KB)
        4. If no article tag found, start from beginning

        Claude Prompt Engineering:
        - System message: Sets expectation for precise JSON output
        - User prompt: Specifies exact JSON structure
        - JSON mode: More reliable structured output
        - Max tokens: Allows for long articles

        Args:
            html_content: Raw HTML content (full page)
            url: Original URL (for metadata)

        Returns:
            Tuple of (article_data dict, tokens_used int)
            - article_data contains: title, author, date, content, summary, topics
            - tokens_used for cost tracking

        Raises:
            Exception: If Claude API fails or returns invalid JSON

        Example Output:
            {
                "title": "AI Breakthrough in Language Models",
                "author": "Jane Smith",
                "date": "2024-01-07",
                "content": "Clean article text...",
                "summary": "Researchers announce major advancement...",
                "topics": ["AI", "Machine Learning", "NLP"],
                "url": "https://example.com/article"
            }
        """
        # Smart HTML truncation - locate article content section
        # This reduces token usage by ~50% while ensuring complete article extraction
        article_start = max(
            html_content.find('<article'),
            html_content.find('class="article'),
            html_content.find('class="post-content'),
            html_content.find('class="entry-content'),
            html_content.find('<main')
        )

        # Extract article section with token limit
        if article_start > 0:
            html_to_analyze = html_content[article_start:article_start + MAX_HTML_LENGTH]
            logger.info(f"Found article section at position {article_start}, extracting {len(html_to_analyze)} chars")
        else:
            html_to_analyze = html_content[:MAX_HTML_LENGTH]
            logger.info(f"No article tag found, using first {len(html_to_analyze)} chars")

        # System message for better Claude instruction following
        system_message = """You are a precise article extraction system. Extract article content from HTML and return valid JSON only.
CRITICAL: All quotes (\") in the content must be escaped as (\\\"). All backslashes (\\) must be escaped as (\\\\). Never truncate content mid-sentence.
Return ONLY the JSON object, no other text."""

        # Prompt with strict JSON output requirements
        # Claude will extract the article and structure it as JSON
        prompt = f"""Extract the main article content from this HTML and return a JSON object with this exact structure:
{{
  "title": "article title",
  "author": "author name or null if not found",
  "date": "publication date or null if not found",
  "content": "clean article text without ads or navigation",
  "summary": "2-3 sentence summary of the article",
  "topics": ["topic1", "topic2", "topic3"]
}}

HTML:
{html_to_analyze}"""

        try:
            logger.info(f"Sending {len(html_to_analyze)} characters to Claude for analysis")

            # Call Claude API with JSON mode for reliable structured output
            message = self.claude_client.messages.create(
                model=os.getenv("ANTHROPIC_LLM_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=MAX_RESPONSE_TOKENS,
                system=system_message,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text.strip()
            logger.info(f"Received response from Claude: {len(response_text)} characters")
            logger.debug(f"Stop reason: {message.stop_reason}")

            # Handle truncated responses (rare with 8K token limit)
            if message.stop_reason == "max_tokens":
                logger.warning("Response was truncated due to max_tokens limit")
                # Try to salvage partial JSON by closing it
                if not response_text.endswith("}"):
                    response_text = response_text.rstrip(",") + "\n}"
                    logger.info("Attempted to close truncated JSON")

            # Clean up response: remove markdown code blocks if present
            # Claude sometimes adds ```json``` despite instructions
            if response_text.startswith("```"):
                logger.debug("Removing markdown code blocks from response")
                parts = response_text.split("```")
                if len(parts) >= 2:
                    response_text = parts[1]
                    if response_text.startswith("json\n"):
                        response_text = response_text[5:].strip()
                    elif response_text.startswith("json"):
                        response_text = response_text[4:].strip()

            # Try to fix common JSON issues
            response_text = response_text.strip()

            # Replace smart quotes with regular quotes to fix JSON parsing
            # Claude sometimes includes smart quotes from article text which breaks JSON
            response_text = response_text.replace('"', '"').replace('"', '"')  # Replace smart double quotes
            response_text = response_text.replace(''', "'").replace(''', "'")  # Replace smart single quotes
            response_text = response_text.replace('—', '-')  # Replace em dash

            if not response_text.endswith("}"):
                logger.warning("Response doesn't end with }, attempting to fix")
                # Find the last complete field
                last_quote = response_text.rfind('"')
                if last_quote > 0:
                    # Truncate to last complete field and close JSON
                    response_text = response_text[:last_quote+1] + "\n}"

            # Parse JSON response
            article_data = json.loads(response_text)
            article_data["url"] = url

            # Calculate total tokens used (input + output)
            # Important for cost tracking: ~$3 per 1M input tokens, ~$15 per 1M output tokens
            tokens_used = message.usage.input_tokens + message.usage.output_tokens
            logger.info(f"Token usage: {message.usage.input_tokens} input + {message.usage.output_tokens} output = {tokens_used} total")

            # Validate extracted content quality
            validation_result = self._validate_content(article_data)
            if not validation_result["valid"]:
                logger.warning(f"Content validation issues: {', '.join(validation_result['warnings'])}")
                # Add validation warnings to article data for transparency
                article_data["validation_warnings"] = validation_result["warnings"]

            logger.info(f"Successfully parsed article: {article_data.get('title', 'Unknown')}")
            return article_data, tokens_used

        except json.JSONDecodeError as e:
            # Log full response for debugging
            logger.error(f"JSON parsing failed: {str(e)}")
            logger.error(f"Response length: {len(response_text)}")
            logger.error(f"Full response: {response_text}")

            # Save failed response to file for inspection
            error_file = Path("downloaded_html") / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"Error: {str(e)}\n")
                f.write(f"Stop reason: {message.stop_reason if 'message' in locals() else 'unknown'}\n")
                f.write(f"\n{'='*50}\n")
                f.write(response_text)
            logger.error(f"Full response saved to {error_file}")

            raise Exception(f"Failed to parse Claude response as JSON: {str(e)}. Response saved to {error_file}")
        except Exception as e:
            logger.error(f"Claude API error: {str(e)}")
            raise Exception(f"Claude API error: {str(e)}")

    def _validate_content(self, article_data: dict) -> dict:
        """
        Validate the quality and completeness of Claude-extracted content.

        This method checks for common extraction issues:
        - Missing or too-short content
        - HTML fragments in extracted text (extraction failure)
        - Generic placeholder values
        - Suspicious content patterns

        Validation helps detect when Claude fails to properly extract content,
        which can happen with unusual HTML structures or paywall-protected articles.

        Args:
            article_data: Extracted article data from Claude

        Returns:
            Dictionary with:
            - valid: bool (True if no critical issues)
            - warnings: list of warning messages

        Example:
            >>> validation = service._validate_content({
            ...     "title": "Short",
            ...     "content": "Too short",
            ...     "summary": ""
            ... })
            >>> print(validation)
            {
                "valid": False,
                "warnings": ["Title is too short", "Content is too short", "Summary is missing"]
            }
        """
        warnings = []

        # Check title quality
        title = article_data.get("title", "")
        if not title or len(title) < 5:
            warnings.append("Title is too short or missing")
        elif title.lower() in ["untitled", "not analyzed yet"]:
            warnings.append("Title appears to be placeholder")

        # Check content quality
        content = article_data.get("content", "")
        if not content:
            warnings.append("Content is empty")
        elif len(content) < 100:
            warnings.append(f"Content is suspiciously short ({len(content)} chars)")
        elif len(content.split()) < 50:
            warnings.append(f"Content has very few words ({len(content.split())} words)")

        # Check for HTML remnants (indicates failed extraction)
        if content and ("<div" in content or "<script" in content or "class=" in content):
            warnings.append("Content may contain HTML fragments")

        # Check summary quality
        summary = article_data.get("summary", "")
        if not summary:
            warnings.append("Summary is missing")
        elif len(summary) < 20:
            warnings.append("Summary is too short")
        elif len(summary) > 1000:
            warnings.append("Summary is unusually long")

        # Check topics
        topics = article_data.get("topics", [])
        if not topics or len(topics) == 0:
            warnings.append("No topics identified")
        elif len(topics) > 10:
            warnings.append(f"Unusually many topics ({len(topics)})")

        # Check for generic/placeholder topics
        generic_topics = {"topic1", "topic2", "topic3", "general", "misc"}
        if topics and any(topic.lower() in generic_topics for topic in topics):
            warnings.append("Topics contain generic placeholders")

        # Determine overall validity
        # Article is valid if it has no critical issues (empty/missing fields)
        critical_warnings = [w for w in warnings if "empty" in w.lower() or "missing" in w.lower()]
        is_valid = len(critical_warnings) == 0

        return {
            "valid": is_valid,
            "warnings": warnings
        }

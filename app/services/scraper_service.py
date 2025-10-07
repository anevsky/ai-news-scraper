"""
Scraper Service - Web Scraping Operations

This module handles the downloading and initial processing of news article HTML.

Responsibilities:
- Download article HTML with proper headers to avoid bot detection
- Extract basic metadata from HTML (title, og:title, etc.)
- Save raw HTML to disk for later AI analysis
- Perform duplicate detection

Design Pattern: Service Layer
- Encapsulates business logic for scraping
- Coordinates between repositories and external HTTP calls
- Provides clean API for routes/controllers
"""

import logging
import re
import html as html_module
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx

from app.repositories import ArticleRepository

logger = logging.getLogger(__name__)

# HTTP request configuration
HTTP_TIMEOUT_SECONDS = 30.0


class ScraperService:
    """
    Service for web scraping operations.

    This service handles the first stage of article processing:
    downloading the raw HTML. The HTML is then analyzed by Claude AI
    in a separate service (AnalyzerService).

    Anti-Bot Measures:
    - Realistic browser headers (Chrome user agent)
    - Proper Accept headers
    - Sec-Ch-Ua headers for Chrome emulation
    - Referer header to appear from Google

    Design Considerations:
    - Separation from AI analysis (different concerns)
    - Duplicate detection before downloading
    - Comprehensive error handling for HTTP failures
    - Metadata extraction as fallback for AI
    """

    def __init__(self):
        """Initialize scraper service with repository."""
        self.article_repo = ArticleRepository()

    def scrape_article(self, url: str, output_dir: Path = Path("downloaded_html")) -> dict:
        """
        Download and save news article HTML.

        This method implements the scraping workflow:
        1. Check for duplicates (avoid re-downloading)
        2. Download HTML with browser headers (anti-bot)
        3. Extract basic title from HTML (fallback for AI)
        4. Save HTML to disk
        5. Save metadata to database

        Args:
            url: Article URL to scrape
            output_dir: Directory to save HTML files (default: downloaded_html)

        Returns:
            Dictionary with:
            - status: 'success' or 'duplicate'
            - filename: Saved HTML filename
            - url: Article URL
            - html_size: Downloaded HTML size in bytes
            - downloaded_at: ISO timestamp
            - article_id: Database article ID
            - message: Status message (for duplicates)

        Raises:
            Exception: If HTTP download fails or file save fails

        Example:
            >>> service = ScraperService()
            >>> result = service.scrape_article("https://techcrunch.com/article")
            >>> if result['status'] == 'success':
            ...     print(f"Downloaded {result['html_size']} bytes to {result['filename']}")
        """
        # Check for duplicate before downloading (saves bandwidth and time)
        existing_article = self.article_repo.get_by_url(url)
        if existing_article:
            logger.warning(f"Duplicate article detected: {url}")
            return {
                "status": "duplicate",
                "message": "This article has already been scraped",
                "url": url,
                "article_id": existing_article["id"]
            }

        # Download HTML with realistic browser headers
        html_content = self._download_html(url)

        # Create output directory if needed
        output_dir.mkdir(exist_ok=True)

        # Generate unique filename based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.html"
        filepath = output_dir / filename

        # Save raw HTML to disk (will be analyzed later)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Saved HTML to {filepath}")

        # Extract basic title from HTML as fallback
        # This provides a title before AI analysis completes
        basic_title = self._extract_basic_title(html_content, url)

        # Save to database with basic title
        article_id = self.article_repo.save_article(url, str(filepath), basic_title)

        if article_id is None:
            # This shouldn't happen since we checked earlier, but handle it
            logger.error(f"Failed to save article to database: {url}")
            raise Exception("Failed to save article to database")

        return {
            "status": "success",
            "filename": filename,
            "url": url,
            "html_size": len(html_content),
            "downloaded_at": datetime.now().isoformat(),
            "article_id": article_id
        }

    def _download_html(self, url: str) -> str:
        """
        Download HTML with browser-like headers to avoid bot detection.

        Many news sites use anti-bot protection (Cloudflare, Akamai) that
        blocks requests without realistic browser headers. This method
        emulates a real Chrome browser to bypass these protections.

        Headers Strategy:
        - User-Agent: Chrome 131 on macOS
        - Accept: HTML/XHTML with proper priorities
        - Sec-Ch-Ua: Chrome version headers
        - Sec-Fetch-*: Navigation security headers
        - Referer: Appear to come from Google search

        Args:
            url: URL to download

        Returns:
            Raw HTML content as string

        Raises:
            Exception: If HTTP request fails (timeout, 404, etc.)
        """
        # Modern browser headers to mimic a real browser request
        # This bypasses most anti-bot protections
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/'
        }

        try:
            logger.info(f"Downloading URL: {url}")

            # Use synchronous httpx Client (compatible with FastAPI's async context)
            # Follow redirects (many news sites redirect to canonical URLs)
            with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()  # Raise exception for 4xx/5xx
                html = response.text

            logger.info(f"Successfully downloaded {len(html)} characters from {url}")
            return html

        except Exception as e:
            logger.error(f"Failed to download {url}: {str(e)}")
            raise Exception(f"Failed to download: {str(e)}")

    def _extract_basic_title(self, html: str, url: str) -> str:
        """
        Extract basic title from HTML using regex patterns.

        This provides a fallback title before Claude AI analysis completes.
        It tries multiple HTML meta tag patterns in order of quality:
        1. <title> tag (cleaned of site name)
        2. og:title Open Graph meta tag
        3. twitter:title Twitter Card meta tag
        4. URL path (as last resort)

        Args:
            html: Raw HTML content
            url: Article URL (used as fallback)

        Returns:
            Extracted title or URL-based fallback

        Example:
            >>> html = '<title>Article Title | TechCrunch</title>'
            >>> title = service._extract_basic_title(html, url)
            >>> print(title)  # "Article Title"
        """
        # Try <title> tag
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            title = html_module.unescape(title_match.group(1).strip())
            # Clean up common patterns like " | Site Name" or " - Site Name"
            title = re.sub(r'\s+[\|\-]\s+.*$', '', title)
            if title and len(title) > 10:
                return title

        # Try og:title meta tag (preferred by most news sites)
        og_title_match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        )
        if og_title_match:
            return html_module.unescape(og_title_match.group(1).strip())

        # Try twitter:title meta tag
        twitter_title_match = re.search(
            r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        )
        if twitter_title_match:
            return html_module.unescape(twitter_title_match.group(1).strip())

        # Fallback: extract from URL path
        try:
            path = urlparse(url).path
            # Get last segment, remove extension, replace hyphens/underscores with spaces
            segments = [s for s in path.split('/') if s]
            if segments:
                last_segment = segments[-1].replace('.html', '').replace('.htm', '')
                title = last_segment.replace('-', ' ').replace('_', ' ').title()
                return title
        except:
            pass

        # Last resort: use domain name
        try:
            domain = urlparse(url).netloc.replace('www.', '')
            return f"Article from {domain}"
        except:
            return "Untitled Article"

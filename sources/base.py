"""
================================================================================
MangaNegus v2.3 - Base Connector
================================================================================
Abstract base class for all manga source connectors.

This follows the HakuNeko/FMD pattern of defining a standard interface:
  1. search(query) -> Find manga by title
  2. get_chapters(manga_id) -> Get chapter list
  3. get_pages(chapter_id) -> Get image URLs

Each source implements these 3 methods according to its specific API/HTML.

RATE LIMITING:
  - Token bucket algorithm prevents hammering servers
  - Each source has configurable rate limits
  - Automatic cooldown on 429/403 responses
================================================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
import time
import threading
import random


# =============================================================================
# LOGGING CALLBACK (avoids circular imports)
# =============================================================================

# Global logger callback - set by app.py on startup
_log_callback: Optional[Callable[[str], None]] = None


def set_log_callback(callback: Callable[[str], None]) -> None:
    """Set the logging callback function. Called by app.py on startup."""
    global _log_callback
    _log_callback = callback


def source_log(msg: str) -> None:
    """Log a message using the registered callback or fallback to print."""
    if _log_callback:
        _log_callback(msg)
    else:
        print(msg)


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class SourceStatus(Enum):
    """Current operational status of a source."""
    ONLINE = "online"
    RATE_LIMITED = "rate_limited"
    CLOUDFLARE = "cloudflare"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class MangaResult:
    """
    Standardized manga result that works across ALL sources.
    
    No matter if we're fetching from MangaDex API or scraping MangaKakalot,
    the frontend always receives this same structure.
    """
    id: str                          # Unique ID (source-specific)
    title: str                       # Display title
    source: str = ""                 # Source identifier
    cover_url: Optional[str] = None  # Cover image URL
    description: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    status: Optional[str] = None     # "ongoing", "completed", "hiatus"
    url: Optional[str] = None        # Direct link to manga page
    genres: List[str] = field(default_factory=list)
    alt_titles: List[str] = field(default_factory=list)
    year: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "cover": self.cover_url,
            "description": self.description,
            "author": self.author,
            "artist": self.artist,
            "status": self.status,
            "url": self.url,
            "genres": self.genres,
            "alt_titles": self.alt_titles,
            "year": self.year
        }


@dataclass
class ChapterResult:
    """Standardized chapter information."""
    id: str                          # Chapter identifier
    chapter: str                     # Chapter number (string for "10.5")
    title: Optional[str] = None      # Chapter title
    volume: Optional[str] = None     # Volume number
    language: str = "en"             # ISO language code
    pages: int = 0                   # Page count if known
    scanlator: Optional[str] = None  # Scanlation group
    published: Optional[str] = None  # Publish date
    url: Optional[str] = None        # Direct URL
    source: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "chapter": self.chapter,
            "title": self.title,
            "volume": self.volume,
            "language": self.language,
            "pages": self.pages,
            "scanlator": self.scanlator,
            "published": self.published,
            "url": self.url,
            "source": self.source
        }


@dataclass
class PageResult:
    """Standardized page/image information."""
    url: str                         # Image URL
    index: int                       # Page number (0-indexed)
    headers: Dict[str, str] = field(default_factory=dict)
    referer: Optional[str] = None    # Required referer header
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "url": self.url,
            "index": self.index,
            "headers": self.headers,
            "referer": self.referer
        }


# =============================================================================
# BASE CONNECTOR CLASS
# =============================================================================

class BaseConnector(ABC):
    """
    Abstract base class for manga source connectors.
    
    INHERITANCE:
        All sources (MangaDex, ComicK, MangaSee, etc.) inherit from this class
        and implement the 3 required methods: search(), get_chapters(), get_pages()
    
    RATE LIMITING:
        Built-in token bucket rate limiter prevents server abuse.
        Configure via rate_limit and rate_limit_burst attributes.
    
    FALLBACK:
        The SourceManager uses status tracking to route requests
        to healthy sources when one is rate-limited or down.
    
    Example:
        class MangaDexConnector(BaseConnector):
            id = "mangadex"
            name = "MangaDex"
            rate_limit = 2.0  # 2 requests per second
            
            def search(self, query, page=1):
                # Implementation here
                pass
    """
    
    # =========================================================================
    # SOURCE CONFIGURATION (Override in subclass)
    # =========================================================================
    
    id: str = "base"                 # Unique identifier
    name: str = "Base Source"        # Display name
    base_url: str = ""               # Root URL
    icon: str = "📚"                 # Emoji for UI
    
    # URL Detection (Override in subclass with domain patterns)
    # Example: url_patterns = [r'https?://(?:www\.)?mangadex\.org/title/([a-f0-9-]+)']
    url_patterns: List[str] = []     # Regex patterns for URL matching
    
    # Rate limiting (requests per second)
    rate_limit: float = 2.0          # Sustained rate
    rate_limit_burst: int = 5        # Burst allowance
    request_timeout: int = 15        # Request timeout seconds
    
    # Feature flags
    supports_latest: bool = False
    supports_popular: bool = False
    requires_cloudflare: bool = False
    is_file_source: bool = False
    
    # Supported languages (ISO codes)
    languages: List[str] = ["en"]
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def __init__(self):
        """Initialize connector with rate limiter state."""
        # Status tracking
        self._status = SourceStatus.UNKNOWN
        self._last_error: Optional[str] = None
        self._failure_count = 0
        self._cooldown_until = 0.0

        # Thread safety
        self._lock = threading.Lock()

        # Token bucket for rate limiting
        self._tokens = float(self.rate_limit_burst)
        self._last_request = time.time()

        # Session will be set by SourceManager
        self.session = None

    # =========================================================================
    # RATE LIMITING (Token Bucket Algorithm)
    # =========================================================================
    
    def _wait_for_rate_limit(self) -> None:
        """
        Block until we have a token available for a request.
        
        TOKEN BUCKET ALGORITHM:
          - Bucket holds up to `rate_limit_burst` tokens
          - Tokens regenerate at `rate_limit` per second
          - Each request consumes 1 token
          - If no tokens, we wait until one regenerates
        
        This prevents hammering servers and respects rate limits.
        """
        with self._lock:
            now = time.time()
            
            # Check if we're in cooldown (from 429/ban)
            if now < self._cooldown_until:
                wait_time = self._cooldown_until - now
                time.sleep(wait_time)
                now = time.time()
            
            # Regenerate tokens based on time elapsed
            time_passed = now - self._last_request
            self._tokens = min(
                self.rate_limit_burst,
                self._tokens + time_passed * self.rate_limit
            )
            
            # If no tokens, calculate wait time
            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.rate_limit
                # Add small jitter to prevent thundering herd
                wait_time += random.uniform(0.05, 0.15)
                time.sleep(wait_time)
                self._tokens = 1
            
            # Consume token
        self._tokens -= 1
        self._last_request = time.time()

    def wait_for_rate_limit(self) -> None:
        """Public wrapper for rate limiting (for downloader use)."""
        self._wait_for_rate_limit()
    
    def _set_cooldown(self, seconds: int) -> None:
        """Set a cooldown period where no requests are made."""
        with self._lock:
            self._cooldown_until = time.time() + seconds
    
    # =========================================================================
    # STATUS MANAGEMENT
    # =========================================================================
    
    def _handle_rate_limit(self, retry_after: int = 60) -> None:
        """Handle 429 Too Many Requests response."""
        with self._lock:
            self._cooldown_until = time.time() + retry_after
            self._status = SourceStatus.RATE_LIMITED
            self._failure_count += 1
    
    def _handle_cloudflare(self) -> None:
        """Handle Cloudflare protection detection."""
        with self._lock:
            self._status = SourceStatus.CLOUDFLARE
            self._cooldown_until = time.time() + 300  # 5 min cooldown
            self._failure_count += 1
    
    def _handle_success(self) -> None:
        """Reset counters on successful request."""
        with self._lock:
            self._status = SourceStatus.ONLINE
            self._failure_count = 0
    
    def _handle_error(self, error: str) -> None:
        """Track errors for fallback decisions."""
        with self._lock:
            self._last_error = error
            self._failure_count += 1
            if self._failure_count >= 5:
                self._status = SourceStatus.OFFLINE
                self._cooldown_until = time.time() + 300
    
    @property
    def status(self) -> SourceStatus:
        """Get current source status, accounting for cooldown expiry."""
        if self._cooldown_until > 0 and time.time() >= self._cooldown_until:
            with self._lock:
                self._status = SourceStatus.UNKNOWN
                self._cooldown_until = 0
        return self._status
    
    @property
    def is_available(self) -> bool:
        """Check if source can accept requests."""
        return self.status in (SourceStatus.ONLINE, SourceStatus.UNKNOWN)
    
    def get_health_info(self) -> Dict[str, Any]:
        """Get health info for status display."""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "status": self.status.value,
            "is_available": self.is_available,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
            "cooldown_remaining": max(0, self._cooldown_until - time.time())
        }
    
    def reset(self) -> None:
        """Reset all error states."""
        with self._lock:
            self._status = SourceStatus.UNKNOWN
            self._failure_count = 0
            self._cooldown_until = 0
            self._last_error = None
            self._tokens = float(self.rate_limit_burst)
    
    # =========================================================================
    # ABSTRACT METHODS (Must implement in subclass)
    # =========================================================================
    
    @abstractmethod
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search for manga by title.
        
        Args:
            query: Search term
            page: Page number (1-indexed)
            
        Returns:
            List of MangaResult matching the query
        """
        pass
    
    @abstractmethod
    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get all chapters for a manga.
        
        Args:
            manga_id: Source-specific manga identifier
            language: ISO language code
            
        Returns:
            List of ChapterResult sorted by chapter number (ascending)
        """
        pass
    
    @abstractmethod
    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page image URLs for a chapter.
        
        Args:
            chapter_id: Source-specific chapter identifier
            
        Returns:
            List of PageResult with image URLs
        """
        pass
    
    # =========================================================================
    # OPTIONAL METHODS (Override if source supports)
    # =========================================================================
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular/trending manga."""
        return []
    
    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        return []
    
    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """Get full details for a specific manga."""
        return None

    def get_download_session(self):
        """Return the preferred session for downloading page images."""
        return self.session
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute."""
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.base_url.rstrip("/") + url
        return self.base_url.rstrip("/") + "/" + url
    
    
    # =========================================================================
    # URL DETECTION METHODS
    # =========================================================================
    
    def matches_url(self, url: str) -> bool:
        """
        Check if this source can handle the given URL.
        
        Args:
            url: Full manga URL to check
            
        Returns:
            True if this source recognizes the URL pattern
        """
        import re
        if not self.url_patterns:
            return False
        
        for pattern in self.url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def extract_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract manga ID from a URL.
        
        Tries all url_patterns and returns the first captured group (manga ID).
        
        Args:
            url: Full manga URL
            
        Returns:
            Manga ID if extracted, None otherwise
            
        Example:
            pattern: r'https?://mangadex\\.org/title/([a-f0-9-]+)'
            URL: 'https://mangadex.org/title/abc-123-def'
            Returns: 'abc-123-def'
        """
        import re
        if not self.url_patterns:
            return None
        
        for pattern in self.url_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match and match.groups():
                return match.group(1)  # Return first captured group
        
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id='{self.id}' status={self.status.value}>"

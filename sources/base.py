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
from typing import List, Optional, Dict, Any, Callable, Union
from enum import Enum
import time
import threading
import random
from manganegus_app.cache import global_rate_limiter


# =============================================================================
# USER AGENT ROTATION POOL
# =============================================================================

USER_AGENTS = [
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Chrome on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Firefox on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    # Firefox on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]


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
    
    def validate(self) -> bool:
        """Validate critical fields are present."""
        if not self.id or not self.title:
            return False
        # Filter out common bad titles from scrape errors
        bad_titles = ['access denied', '403 forbidden', 'cloudflare', 'just a moment', 'attention required']
        if any(b in self.title.lower() for b in bad_titles):
            return False
        return True

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
    
    def validate(self) -> bool:
        """Validate chapter data."""
        if not self.id or not self.chapter:
            return False
        return True

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

    RATE LIMITING:
        Uses GlobalRateLimiter (Redis-backed) if available to ensure shared limits
        across Gunicorn workers. Falls back to internal token bucket.

    RETRY LOGIC:
        fetch_with_retry() provides exponential backoff with jitter and UA rotation
        for handling transient failures, rate limits, and Cloudflare blocks.
    """

    id: str = "base"                 # Unique identifier
    name: str = "Base Source"        # Display name
    base_url: str = ""               # Root URL
    icon: str = "📚"                 # Emoji for UI

    # URL Detection
    url_patterns: List[str] = []     # Regex patterns for URL matching

    # Rate limiting
    rate_limit: float = 2.0          # Sustained rate
    rate_limit_burst: int = 5        # Burst allowance
    request_timeout: int = 15        # Request timeout seconds

    # Retry configuration
    MAX_RETRIES: int = 4             # Maximum retry attempts
    BACKOFF_BASE: float = 2.0        # Base seconds for exponential backoff
    BACKOFF_MAX: float = 60.0        # Maximum backoff time

    # Feature flags
    supports_latest: bool = False
    supports_popular: bool = False
    requires_cloudflare: bool = False
    is_file_source: bool = False

    # Supported languages
    languages: List[str] = ["en"]
    
    def __init__(self):
        """Initialize connector with rate limiter state."""
        # Status tracking
        self._status = SourceStatus.UNKNOWN
        self._last_error: Optional[str] = None
        self._failure_count = 0
        self._cooldown_until = 0.0
        self._mirror_index = 0
        self._last_mirror_switch = 0.0

        # Thread safety
        self._lock = threading.Lock()

        # Token bucket for rate limiting
        self._tokens = float(self.rate_limit_burst)
        self._last_request = time.time()

        # Session will be set by SourceManager
        self.session = None

    def _validate_response(self, text: str, url: str = "") -> bool:
        """
        Check response text for common soft-ban/captcha signatures.
        Returns False if the response is invalid/blocked.
        """
        if not text:
            return False
            
        text_lower = text.lower()
        block_signatures = [
            'checking your browser',
            'access denied',
            '403 forbidden',
            'cloudflare',
            'attention required',
            'security check',
            'enable javascript'
        ]
        
        if any(sig in text_lower for sig in block_signatures):
            if len(text) < 5000:
                source_log(f"[{self.id}] Blocked/Captcha detected at {url}")
                self._handle_cloudflare()
                return False

        return True

    def _get_random_user_agent(self) -> str:
        """Get a random User-Agent from the pool."""
        return random.choice(USER_AGENTS)

    def fetch_with_retry(
        self,
        url: str,
        method: str = "GET",
        validate_response: bool = True,
        **kwargs
    ) -> Any:
        """
        Fetch URL with exponential backoff, jitter, and UA rotation.

        Args:
            url: The URL to fetch
            method: HTTP method (GET or POST)
            validate_response: Whether to check for Cloudflare/block signatures
            **kwargs: Additional arguments passed to session.request()

        Returns:
            Response object on success

        Raises:
            Last exception encountered after all retries exhausted
        """
        if not self.session:
            raise RuntimeError(f"[{self.id}] Session not initialized")

        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Wait for rate limit before each attempt
                self._wait_for_rate_limit()

                # Rotate User-Agent on each attempt
                headers = kwargs.get('headers', {}).copy()
                if 'User-Agent' not in headers:
                    headers['User-Agent'] = self._get_random_user_agent()
                kwargs['headers'] = headers

                # Set timeout if not specified
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = self.request_timeout

                # Make the request
                if method.upper() == "POST":
                    response = self.session.post(url, **kwargs)
                else:
                    response = self.session.get(url, **kwargs)

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    source_log(f"[{self.id}] Rate limited (429), waiting {retry_after}s")
                    self._handle_rate_limit(retry_after)
                    time.sleep(retry_after)
                    continue

                # Handle Cloudflare/forbidden (403)
                if response.status_code == 403:
                    source_log(f"[{self.id}] Forbidden (403) at {url}, attempt {attempt + 1}/{self.MAX_RETRIES}")
                    self._handle_cloudflare()
                    wait = min(self.BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1), self.BACKOFF_MAX)
                    time.sleep(wait)
                    continue

                # Handle server errors (5xx)
                if response.status_code >= 500:
                    source_log(f"[{self.id}] Server error ({response.status_code}) at {url}, attempt {attempt + 1}/{self.MAX_RETRIES}")
                    wait = min(self.BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1), self.BACKOFF_MAX)
                    time.sleep(wait)
                    continue

                # Raise for other client errors
                response.raise_for_status()

                # Validate response content for soft blocks
                if validate_response and hasattr(response, 'text'):
                    if not self._validate_response(response.text, url):
                        wait = min(self.BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1), self.BACKOFF_MAX)
                        time.sleep(wait)
                        continue

                # Success
                self._handle_success()
                return response

            except Exception as e:
                last_error = e
                self._handle_error(str(e))
                source_log(f"[{self.id}] Request failed ({type(e).__name__}): {e}, attempt {attempt + 1}/{self.MAX_RETRIES}")

                # Exponential backoff with jitter
                wait = min(self.BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1), self.BACKOFF_MAX)
                time.sleep(wait)

        # All retries exhausted
        source_log(f"[{self.id}] All {self.MAX_RETRIES} retries exhausted for {url}")
        if last_error:
            raise last_error
        raise RuntimeError(f"[{self.id}] Failed to fetch {url} after {self.MAX_RETRIES} retries")

    def fetch_image_with_retry(
        self,
        url: str,
        referer: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> bytes:
        """
        Fetch image with retry logic optimized for image loading.

        Handles common image loading failures:
        - 403 Forbidden (hotlink protection, requires referer)
        - 503 Service Unavailable (server overload)
        - Cloudflare challenges
        - Connection timeouts

        Args:
            url: Image URL to fetch
            referer: Referer header (often required for hotlink protection)
            extra_headers: Additional headers to include
            **kwargs: Additional arguments passed to fetch_with_retry()

        Returns:
            Image content as bytes

        Raises:
            Exception on failure after all retries
        """
        headers = extra_headers.copy() if extra_headers else {}

        # Set referer for hotlink protection bypass
        if referer:
            headers['Referer'] = referer
        elif self.base_url:
            headers['Referer'] = self.base_url

        # Common image request headers
        headers.setdefault('Accept', 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8')
        headers.setdefault('Accept-Language', 'en-US,en;q=0.9')
        headers.setdefault('Sec-Fetch-Dest', 'image')
        headers.setdefault('Sec-Fetch-Mode', 'no-cors')
        headers.setdefault('Sec-Fetch-Site', 'cross-site')

        # Use longer timeout for images
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30

        # Don't validate response text for binary image data
        response = self.fetch_with_retry(
            url,
            headers=headers,
            validate_response=False,
            **kwargs
        )

        return response.content

    def fetch_html_raw(self, url: str) -> str:
        """
        Hard scrap: Fetch raw HTML using robust retry logic and browser impersonation.
        This ensures we get the content even if standard requests struggle.
        """
        response = self.fetch_with_retry(url, method="GET", validate_response=True)
        return response.text

    def extract_images_raw(self, html: str) -> List[str]:
        """
        Fallback: Extract potential image URLs from raw HTML using regex.
        Useful when DOM parsing fails due to broken HTML, JS rendering, or anti-bot obfuscation.
        """
        import re
        # Look for common image extensions in quotes (broad pattern)
        pattern = r'[\"\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp|avif)[^"\']*)[\"\']'
        matches = re.findall(pattern, html, re.IGNORECASE)
        
        # Clean up matches
        cleaned = []
        for m in matches:
            # Remove backslashes from escaped JSON
            url = m.replace('\\', '')
            if 'http' in url:
                cleaned.append(url)
        
        return list(set(cleaned))

    def _wait_for_rate_limit(self) -> None:
        """
        Block until we have a token available for a request.
        Uses GlobalRateLimiter (Redis-backed) if available.
        """
        # 1. Global Rate Limit Check (Redis)
        wait_time = global_rate_limiter.check(self.id, self.rate_limit, self.rate_limit_burst)
        if wait_time > 0:
            time.sleep(wait_time)
            return

        # 2. Local Fallback
        with self._lock:
            now = time.time()
            
            # Check cooldown
            if now < self._cooldown_until:
                wait_time = self._cooldown_until - now
                time.sleep(wait_time)
                now = time.time()
            
            # Regenerate tokens
            time_passed = now - self._last_request
            self._tokens = min(
                self.rate_limit_burst,
                self._tokens + time_passed * self.rate_limit
            )
            
            # Wait if no tokens
            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.rate_limit
                wait_time += random.uniform(0.05, 0.15)
                time.sleep(wait_time)
                self._tokens = 1

            # Consume token
            self._tokens -= 1
            self._last_request = time.time()

    def wait_for_rate_limit(self) -> None:
        """Public wrapper for rate limiting."""
        self._wait_for_rate_limit()
    
    def _set_cooldown(self, seconds: int) -> None:
        """Set a cooldown period."""
        with self._lock:
            self._cooldown_until = time.time() + seconds

    def _rotate_mirror(self, reason: str) -> None:
        mirrors = getattr(self, "MIRRORS", None)
        if not mirrors or not isinstance(mirrors, list) or len(mirrors) < 2:
            return
        now = time.time()
        if (now - self._last_mirror_switch) < 30:
            return
        self._last_mirror_switch = now
        if self.base_url in mirrors:
            idx = mirrors.index(self.base_url)
            next_idx = (idx + 1) % len(mirrors)
        else:
            next_idx = (self._mirror_index + 1) % len(mirrors)
        self._mirror_index = next_idx
        self.base_url = mirrors[next_idx]
        source_log(f"[{self.id}] 🔁 Switched mirror to {self.base_url} ({reason})")
    
    def _handle_rate_limit(self, retry_after: int = 60) -> None:
        with self._lock:
            self._cooldown_until = time.time() + retry_after
            self._status = SourceStatus.RATE_LIMITED
            self._failure_count += 1
        self._rotate_mirror("rate_limited")
    
    def _handle_cloudflare(self) -> None:
        with self._lock:
            self._status = SourceStatus.CLOUDFLARE
            self._cooldown_until = time.time() + 300
            self._failure_count += 1
        self._rotate_mirror("cloudflare")
    
    def _handle_success(self) -> None:
        with self._lock:
            self._status = SourceStatus.ONLINE
            self._failure_count = 0
    
    def _handle_error(self, error: str) -> None:
        with self._lock:
            self._last_error = error
            self._failure_count += 1
            if self._failure_count >= 5:
                self._status = SourceStatus.OFFLINE
                self._cooldown_until = time.time() + 300
        if self._failure_count >= 2:
            self._rotate_mirror("error")
    
    @property
    def status(self) -> SourceStatus:
        if self._cooldown_until > 0 and time.time() >= self._cooldown_until:
            with self._lock:
                self._status = SourceStatus.UNKNOWN
                self._cooldown_until = 0
        return self._status
    
    @property
    def is_available(self) -> bool:
        return self.status in (SourceStatus.ONLINE, SourceStatus.UNKNOWN)
    
    def get_health_info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "status": self.status.value,
            "is_available": self.is_available,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
            "cooldown_remaining": max(0, self._cooldown_until - time.time()),
            "rate_limit_per_minute": int(self.rate_limit * 60),
            "rate_limit_burst": int(self.rate_limit_burst),
            "rate_limit_tokens": round(self._tokens, 2)
        }
    
    def reset(self) -> None:
        with self._lock:
            self._status = SourceStatus.UNKNOWN
            self._failure_count = 0
            self._cooldown_until = 0
            self._last_error = None
            self._tokens = float(self.rate_limit_burst)
    
    @abstractmethod
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        pass
    
    @abstractmethod
    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        pass
    
    @abstractmethod
    def get_pages(self, chapter_id: str) -> List["PageResult"]:
        pass
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        return []
    
    def get_latest(self, page: int = 1) -> List[MangaResult]:
        return []
    
    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        return None

    def get_download_session(self):
        return self.session
    
    def _absolute_url(self, url: str) -> str:
        if not url: return ""
        if url.startswith(("http://", "https://")): return url
        if url.startswith("//"): return "https:" + url
        if url.startswith("/"): return self.base_url.rstrip("/") + url
        return self.base_url.rstrip("/") + "/" + url
    
    def matches_url(self, url: str) -> bool:
        import re
        if not self.url_patterns: return False
        for pattern in self.url_patterns:
            if re.search(pattern, url, re.IGNORECASE): return True
        return False
    
    def extract_id_from_url(self, url: str) -> Optional[str]:
        import re
        if not self.url_patterns: return None
        for pattern in self.url_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match and match.groups(): return match.group(1)
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id='{self.id}' status={self.status.value}>"
"""
Discovery Service - MangaDex-first discovery with Jikan metadata enrichment.

Provides trending, discover (hidden gems), and popular manga endpoints using
MangaDex for discovery algorithms, enriched with Jikan metadata for covers.

Strategy:
  - Use MangaDex API for discovery (trending/popular/discover algorithms)
  - Enrich results with Jikan metadata (covers, ratings, synopsis)
  - Keep MangaDex IDs for chapter fetching

Algorithms:
  - Trending: Ongoing manga with recent chapters (latestUploadedChapter desc)
  - Discover: Lesser-known manga (offset 500+, recent activity)
  - Popular: High followers + ongoing status

Caching:
  - Trending: 30 min TTL
  - Discover: 60 min TTL
  - Popular: 30 min TTL
"""

import time
import hashlib
import threading
import requests
from typing import Optional, Dict, List, Any
from collections import OrderedDict


class DiscoveryCache:
    """Thread-safe in-memory cache for discovery results with configurable TTL."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, cache_type: str, page: int, limit: int) -> str:
        """Generate cache key from type, page, and limit."""
        data = f"{cache_type}:{page}:{limit}"
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, cache_type: str, page: int, limit: int, ttl: int) -> Optional[Dict]:
        """Get cached results if not expired."""
        key = self._make_key(cache_type, page, limit)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if time.time() - entry['timestamp'] > ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1

            return entry['data']

    def set(self, cache_type: str, page: int, limit: int, data: List[Dict]):
        """Cache discovery results."""
        key = self._make_key(cache_type, page, limit)

        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._cache.popitem(last=False)

            self._cache[key] = {
                'data': data,
                'timestamp': time.time()
            }

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2)
            }


class DiscoveryService:
    """
    MangaDex-first discovery service with Jikan fallback.

    Provides trending, discover (hidden gems), and popular manga endpoints.
    """

    MANGADEX_API = "https://api.mangadex.org"
    USER_AGENT = "MangaNegus/3.0 (https://github.com/bookers1897/Manga-Negus)"
    CONTENT_RATINGS = ["safe", "suggestive", "erotica"]

    # TTL values in seconds
    TTL_TRENDING = 30 * 60   # 30 minutes
    TTL_DISCOVER = 60 * 60   # 60 minutes
    TTL_POPULAR = 30 * 60    # 30 minutes

    # Rate limiting - MangaDex allows 5/sec, use 4/sec for safety
    RATE_LIMIT_DELAY = 0.25  # ~4 req/sec

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.USER_AGENT,
            'Accept': 'application/json'
        })
        self.cache = DiscoveryCache()
        self._last_request_time = 0
        self._lock = threading.Lock()

    def _rate_limit(self):
        """Ensure we don't exceed MangaDex rate limit."""
        with self._lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_DELAY:
                time.sleep(self.RATE_LIMIT_DELAY - elapsed)
            self._last_request_time = time.time()

    def _request(self, endpoint: str, params: Optional[Dict] = None, retries: int = 3) -> Optional[Dict]:
        """Make a rate-limited API request with retries."""
        self._rate_limit()

        url = f"{self.MANGADEX_API}{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    self._log(f"Rate limited, waiting {retry_after}s...")
                    if attempt < retries - 1:
                        time.sleep(retry_after)
                        continue
                    return None

                if response.status_code == 403:
                    self._log("MangaDex temporary ban, falling back to Jikan")
                    return None

                if response.status_code >= 500:
                    if attempt < retries - 1:
                        wait = (2 ** attempt) + 1
                        time.sleep(wait)
                        continue

                self._log(f"MangaDex error: HTTP {response.status_code}")
                return None

            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                self._log(f"MangaDex request error: {e}")
                return None

        return None

    def _log(self, msg: str):
        """Log message using app's logging system."""
        try:
            from manganegus_app.log import log
            log(f"[Discovery] {msg}")
        except ImportError:
            print(f"[Discovery] {msg}")

    def _get_english_title(self, manga_data: Dict) -> str:
        """Extract the best English title from manga data."""
        attrs = manga_data.get("attributes", {})
        titles = attrs.get("title", {})
        alt_titles = attrs.get("altTitles", [])

        # Check main title for English
        if "en" in titles:
            return titles["en"]

        # Check alternate titles for English
        for alt in alt_titles:
            if isinstance(alt, dict) and "en" in alt:
                return alt["en"]

        # Try romaji (Japanese romanized)
        if "ja-ro" in titles:
            return titles["ja-ro"]

        for alt in alt_titles:
            if isinstance(alt, dict) and "ja-ro" in alt:
                return alt["ja-ro"]

        # Try Japanese
        if "ja" in titles:
            return titles["ja"]

        # Fallback to any available title
        if titles:
            return next(iter(titles.values()))

        for alt in alt_titles:
            if isinstance(alt, dict):
                return next(iter(alt.values()), "Unknown")

        return "Unknown"

    def _extract_cover(self, manga_data: Dict) -> Optional[str]:
        """Extract cover URL from manga relationships."""
        manga_id = manga_data.get("id", "")

        for rel in manga_data.get("relationships", []):
            if rel.get("type") == "cover_art":
                filename = rel.get("attributes", {}).get("fileName")
                if filename:
                    return f"https://uploads.mangadex.org/covers/{manga_id}/{filename}.256.jpg"
        return None

    def _parse_manga(self, data: Dict) -> Dict:
        """Parse MangaDex manga data into frontend-compatible format."""
        attrs = data.get("attributes", {})
        rels = data.get("relationships", [])

        # Get best English title
        title = self._get_english_title(data)

        # Get description (prefer English)
        desc = attrs.get("description", {})
        description = desc.get("en") if isinstance(desc, dict) else None
        if not description and isinstance(desc, dict):
            description = next(iter(desc.values()), None)

        # Get author from relationships
        author = None
        for rel in rels:
            if rel.get("type") == "author":
                author = rel.get("attributes", {}).get("name")
                break

        # Get genres from tags
        genres = []
        for tag in attrs.get("tags", []):
            tag_name = tag.get("attributes", {}).get("name", {})
            if isinstance(tag_name, dict):
                en_name = tag_name.get("en")
                if en_name:
                    genres.append(en_name)
            elif isinstance(tag_name, str):
                genres.append(tag_name)

        # Map status to frontend format
        status_map = {
            'ongoing': 'Ongoing',
            'completed': 'Completed',
            'hiatus': 'Hiatus',
            'cancelled': 'Cancelled'
        }
        raw_status = attrs.get("status", "")
        status = status_map.get(raw_status, raw_status.capitalize() if raw_status else "Unknown")

        return {
            'id': data.get("id", ""),
            'source': 'mangadex',  # Critical for routing to MangaDex chapters
            'title': title,
            'cover_url': self._extract_cover(data),  # Fallback, will be replaced by Jikan
            'synopsis': description,
            'status': status,
            'year': attrs.get("year"),
            'genres': genres[:8],  # Limit to 8 genres
            'author': author,
            'rating': {'average': None, 'count': None},  # Will be enriched by Jikan
            'url': f"https://mangadex.org/title/{data.get('id')}"
        }

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison (lowercase, remove special chars)."""
        import re
        if not title:
            return ""
        # Lowercase and remove special characters
        normalized = re.sub(r'[^\w\s]', '', title.lower())
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized

    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar enough to be the same manga."""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)

        if not norm1 or not norm2:
            return False

        # Exact match after normalization
        if norm1 == norm2:
            return True

        # One contains the other (for cases like "Solo Leveling" vs "Solo Leveling (Novel)")
        if norm1 in norm2 or norm2 in norm1:
            return True

        # Check word overlap ratio
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        if not words1 or not words2:
            return False

        overlap = len(words1 & words2)
        min_words = min(len(words1), len(words2))

        # At least 70% word overlap
        return overlap / min_words >= 0.7

    def _enrich_with_jikan(self, manga_list: List[Dict]) -> List[Dict]:
        """
        Enrich MangaDex results with Jikan metadata (covers, ratings, etc.).

        Keeps MangaDex id and source for chapter fetching, but replaces
        cover_url and adds rating/metadata from Jikan/MAL.

        Uses strict title matching to avoid incorrect enrichment.
        """
        if not manga_list:
            return manga_list

        try:
            from manganegus_app.jikan_api import get_jikan_client
            jikan = get_jikan_client()
        except Exception as e:
            self._log(f"Could not load Jikan client: {e}")
            return manga_list

        enriched = []
        for manga in manga_list:
            title = manga.get('title', '')
            if not title:
                enriched.append(manga)
                continue

            try:
                # Search Jikan for this manga by title (get more results for better matching)
                jikan_results = jikan.search_manga(title, limit=5)

                matched_jikan = None
                if jikan_results:
                    # Find the best matching result by title
                    for jikan_data in jikan_results:
                        jikan_title = jikan_data.get('title', '')
                        jikan_title_en = jikan_data.get('title_english', '')

                        if self._titles_match(title, jikan_title) or self._titles_match(title, jikan_title_en):
                            matched_jikan = jikan_data
                            break

                if matched_jikan:
                    # Merge Jikan metadata but keep MangaDex id and source
                    enriched_manga = {
                        **manga,  # Keep all MangaDex data (id, source, url)
                        # Replace with Jikan data for better covers/metadata
                        'cover_url': matched_jikan.get('cover_url') or manga.get('cover_url'),
                        'synopsis': matched_jikan.get('synopsis') or manga.get('synopsis'),
                        'rating': matched_jikan.get('rating') or manga.get('rating'),
                        'genres': matched_jikan.get('genres') or manga.get('genres', []),
                        'author': matched_jikan.get('author') or manga.get('author'),
                        'status': matched_jikan.get('status') or manga.get('status'),
                        'year': matched_jikan.get('year') or manga.get('year'),
                        # Add MAL ID for reference
                        'mal_id': matched_jikan.get('mal_id'),
                    }
                    enriched.append(enriched_manga)
                    self._log(f"Enriched: {title[:30]} -> MAL {matched_jikan.get('mal_id')}")
                else:
                    # No good Jikan match, keep original MangaDex data
                    enriched.append(manga)
                    self._log(f"No Jikan match for: {title[:30]}")

            except Exception as e:
                self._log(f"Enrichment error for '{title[:20]}': {e}")
                enriched.append(manga)

        return enriched

    def get_trending(self, page: int = 1, limit: int = 20) -> List[Dict]:
        """
        Get trending manga - ongoing with recent chapter activity.

        Algorithm: status=ongoing, order by latestUploadedChapter desc
        """
        # Check cache first
        cached = self.cache.get('trending', page, limit, self.TTL_TRENDING)
        if cached is not None:
            self._log(f"Trending page {page}: cache hit")
            return cached

        self._log(f"Trending page {page}: fetching from MangaDex...")

        offset = (page - 1) * limit

        params = {
            "limit": min(limit, 25),
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "availableTranslatedLanguage[]": ["en"],
            "status[]": ["ongoing"],
            "order[latestUploadedChapter]": "desc"
        }

        data = self._request("/manga", params)

        if not data:
            self._log("MangaDex failed, falling back to Jikan trending")
            return self._jikan_fallback_trending(page, limit)

        results = []
        for manga in data.get("data", []):
            try:
                results.append(self._parse_manga(manga))
            except Exception as e:
                self._log(f"Parse error: {e}")
                continue

        # Cache results (skip slow Jikan enrichment - use MangaDex covers directly)
        if results:
            self.cache.set('trending', page, limit, results)
            self._log(f"Trending: cached {len(results)} results")

        return results

    def get_discover(self, page: int = 1, limit: int = 20) -> List[Dict]:
        """
        Get discover/hidden gems - lesser-known manga with recent activity.

        Algorithm: offset 500+ to skip top popular, order by latestUploadedChapter desc
        """
        # Check cache first
        cached = self.cache.get('discover', page, limit, self.TTL_DISCOVER)
        if cached is not None:
            self._log(f"Discover page {page}: cache hit")
            return cached

        self._log(f"Discover page {page}: fetching from MangaDex...")

        # Skip top 500 to find lesser-known manga
        base_offset = 500
        offset = base_offset + ((page - 1) * limit)

        params = {
            "limit": min(limit, 25),
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "availableTranslatedLanguage[]": ["en"],
            "order[latestUploadedChapter]": "desc"
        }

        data = self._request("/manga", params)

        if not data:
            self._log("MangaDex failed, falling back to Jikan hidden gems")
            return self._jikan_fallback_discover(page, limit)

        results = []
        for manga in data.get("data", []):
            try:
                results.append(self._parse_manga(manga))
            except Exception as e:
                self._log(f"Parse error: {e}")
                continue

        # Cache results (skip slow Jikan enrichment - use MangaDex covers directly)
        if results:
            self.cache.set('discover', page, limit, results)
            self._log(f"Discover: cached {len(results)} results")

        return results

    def get_popular(self, page: int = 1, limit: int = 20) -> List[Dict]:
        """
        Get popular manga - high followers, prioritize ongoing/active.

        Algorithm: order by followedCount desc, prefer ongoing status
        """
        # Check cache first
        cached = self.cache.get('popular', page, limit, self.TTL_POPULAR)
        if cached is not None:
            self._log(f"Popular page {page}: cache hit")
            return cached

        self._log(f"Popular page {page}: fetching from MangaDex...")

        offset = (page - 1) * limit

        params = {
            "limit": min(limit, 25),
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "availableTranslatedLanguage[]": ["en"],
            "status[]": ["ongoing", "completed"],  # Active manga only
            "order[followedCount]": "desc"
        }

        data = self._request("/manga", params)

        if not data:
            self._log("MangaDex failed, falling back to Jikan popular")
            return self._jikan_fallback_popular(page, limit)

        results = []
        for manga in data.get("data", []):
            try:
                results.append(self._parse_manga(manga))
            except Exception as e:
                self._log(f"Parse error: {e}")
                continue

        # Cache results (skip slow Jikan enrichment - use MangaDex covers directly)
        if results:
            self.cache.set('popular', page, limit, results)
            self._log(f"Popular: cached {len(results)} results")

        return results

    def _jikan_fallback_trending(self, page: int, limit: int) -> List[Dict]:
        """Fallback to Jikan for trending manga."""
        try:
            from manganegus_app.jikan_api import get_jikan_client
            jikan = get_jikan_client()
            results = jikan.get_seasonal_manga(limit=limit, page=page)
            if not results:
                results = jikan.get_top_manga(limit=limit, page=page)
            return results or []
        except Exception as e:
            self._log(f"Jikan fallback error: {e}")
            return []

    def _jikan_fallback_discover(self, page: int, limit: int) -> List[Dict]:
        """Fallback to Jikan for discover/hidden gems."""
        try:
            from manganegus_app.jikan_api import get_jikan_client
            jikan = get_jikan_client()
            return jikan.get_hidden_gems(limit=limit, page=page) or []
        except Exception as e:
            self._log(f"Jikan fallback error: {e}")
            return []

    def _jikan_fallback_popular(self, page: int, limit: int) -> List[Dict]:
        """Fallback to Jikan for popular manga."""
        try:
            from manganegus_app.jikan_api import get_jikan_client
            jikan = get_jikan_client()
            return jikan.get_blended_popular(limit=limit, page=page) or []
        except Exception as e:
            self._log(f"Jikan fallback error: {e}")
            return []

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return self.cache.stats()


# Singleton instance
_discovery_service = None
_service_lock = threading.Lock()


def get_discovery_service() -> DiscoveryService:
    """Get singleton DiscoveryService instance."""
    global _discovery_service
    with _service_lock:
        if _discovery_service is None:
            _discovery_service = DiscoveryService()
        return _discovery_service

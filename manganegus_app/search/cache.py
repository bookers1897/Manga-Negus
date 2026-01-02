"""
Cache layer for smart search results.

Design:
  - In-memory dict cache (simple, no external dependencies)
  - TTL-based expiration (1 hour)
  - Thread-safe with locks
  - LRU eviction when cache size exceeds limit

Usage:
    cache = SearchCache(ttl=3600, max_size=1000)

    # Store results
    cache.set(query="naruto", data=results, sources=["mangadex", "weebcentral"])

    # Retrieve results
    cached = cache.get(query="naruto", sources=["mangadex", "weebcentral"])

    # Cache stats
    stats = cache.stats()
"""

import time
import hashlib
import threading
from typing import Optional, Dict, Any, List
from collections import OrderedDict


class SearchCache:
    """Thread-safe in-memory cache for search results."""

    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        """
        Initialize cache.

        Args:
            ttl: Time-to-live in seconds (default: 1 hour)
            max_size: Maximum cache entries (default: 1000)
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str, sources: Optional[List[str]] = None) -> str:
        """
        Generate cache key from query and sources.

        Args:
            query: Search query string
            sources: List of source IDs (optional)

        Returns:
            MD5 hash of normalized query + sources
        """
        sources_str = ','.join(sorted(sources)) if sources else 'default'
        data = f"{query.lower().strip()}:{sources_str}"
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, query: str, sources: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Get cached results if not expired.

        Args:
            query: Search query string
            sources: List of source IDs (optional)

        Returns:
            Cached data dict or None if not found/expired
        """
        key = self._make_key(query, sources)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if time.time() - entry['timestamp'] > self.ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1

            return entry['data']

    def set(self, query: str, data: Dict, sources: Optional[List[str]] = None):
        """
        Cache search results.

        Args:
            query: Search query string
            data: Search results to cache (must be JSON-serializable)
            sources: List of source IDs (optional)
        """
        key = self._make_key(query, sources)

        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._cache.popitem(last=False)

            self._cache[key] = {
                'data': data,
                'timestamp': time.time()
            }

    def clear(self):
        """Clear all cache entries and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache metrics:
                - size: Current number of entries
                - max_size: Maximum capacity
                - ttl: Time-to-live in seconds
                - hits: Cache hit count
                - misses: Cache miss count
                - hit_rate: Percentage of cache hits
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2)
            }

    def evict_expired(self) -> int:
        """
        Manually evict all expired entries.

        Returns:
            Number of entries evicted
        """
        now = time.time()
        evicted = 0

        with self._lock:
            # Collect expired keys
            expired_keys = [
                key for key, entry in self._cache.items()
                if now - entry['timestamp'] > self.ttl
            ]

            # Remove expired entries
            for key in expired_keys:
                del self._cache[key]
                evicted += 1

        return evicted

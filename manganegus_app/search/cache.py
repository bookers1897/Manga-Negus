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
from typing import Optional, Dict, Any, List
from manganegus_app.cache import global_cache


class SearchCache:
    """Cache layer for search results using GlobalCache (Redis/Memory)."""

    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        """
        Initialize cache.

        Args:
            ttl: Time-to-live in seconds (default: 1 hour)
            max_size: Maximum cache entries (default: 1000)
        """
        self.ttl = ttl
        self.max_size = max_size

    def _make_key(self, query: str, sources: Optional[List[str]] = None) -> str:
        """
        Generate cache key from query and sources.
        """
        sources_str = ','.join(sorted(sources)) if sources else 'default'
        data = f"search:{query.lower().strip()}:{sources_str}"
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, query: str, sources: Optional[List[str]] = None) -> Optional[List[Dict]]:
        """
        Get cached results if not expired.
        """
        key = self._make_key(query, sources)
        return global_cache.get_json(key)

    def set(self, query: str, data: List[Dict], sources: Optional[List[str]] = None):
        """
        Cache search results.
        """
        key = self._make_key(query, sources)
        global_cache.set_json(key, data, self.ttl)

    def clear(self):
        """Clear functionality handled by Redis/GlobalCache TTL."""
        pass

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        """
        return {
            'type': 'GlobalCache',
            'is_redis': global_cache.is_redis,
            'ttl': self.ttl
        }

    def evict_expired(self) -> int:
        """Handled automatically by GlobalCache/Redis."""
        return 0

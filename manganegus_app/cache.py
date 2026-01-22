"""
================================================================================
MangaNegus v4.1 - Global Cache & Rate Limiting Utility
================================================================================
Provides a unified interface for caching and rate limiting with Redis backend.
Falls back to in-memory storage if Redis is unavailable.

Ensures consistency across multi-worker deployments (Gunicorn/Celery).
================================================================================
"""

import os
import json
import time
import logging
import threading
from typing import Any, Optional, Dict, List, Union
from collections import OrderedDict

# Try to import redis
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

logger = logging.getLogger(__name__)

class RedisBackend:
    """Redis-based storage for shared state."""
    def __init__(self, url: str):
        self.client = redis.from_url(url, decode_responses=True)
        self.url = url

    def get(self, key: str) -> Optional[str]:
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET failed: {e}")
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        try:
            self.client.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Redis SET failed: {e}")

    def delete(self, key: str):
        try:
            self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis DELETE failed: {e}")

    def incr(self, key: str, amount: int = 1) -> int:
        try:
            return self.client.incr(key, amount)
        except Exception:
            return 0

    def expire(self, key: str, ttl: int):
        try:
            self.client.expire(key, ttl)
        except Exception:
            pass

    def hgetall(self, key: str) -> Dict[str, str]:
        try:
            return self.client.hgetall(key)
        except Exception:
            return {}

    def hset(self, key: str, mapping: Dict[str, str]):
        try:
            self.client.hset(key, mapping=mapping)
        except Exception:
            pass

class MemoryBackend:
    """Fallback in-memory storage."""
    def __init__(self, max_size: int = 1000):
        self._data: OrderedDict = OrderedDict()
        self._expires: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.max_size = max_size

    def _is_expired(self, key: str) -> bool:
        expiry = self._expires.get(key)
        if expiry and time.time() > expiry:
            return True
        return False

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key not in self._data:
                return None
            if self._is_expired(key):
                del self._data[key]
                del self._expires[key]
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        with self._lock:
            if len(self._data) >= self.max_size and key not in self._data:
                self._data.popitem(last=False)
            self._data[key] = value
            if ttl:
                self._expires[key] = time.time() + ttl
            elif key in self._expires:
                del self._expires[key]

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)
            self._expires.pop(key, None)

class GlobalCache:
    """Unified cache interface with auto-fallback."""
    def __init__(self, prefix: str = "manganegus:"):
        self.prefix = prefix
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('CELERY_BROKER_URL')
        
        if HAS_REDIS and redis_url:
            try:
                self.backend = RedisBackend(redis_url)
                # Test connection
                self.backend.client.ping()
                self.is_redis = True
                logger.info(f"🚀 GlobalCache initialized with Redis: {redis_url}")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed, falling back to memory: {e}")
                self.backend = MemoryBackend()
                self.is_redis = False
        else:
            self.backend = MemoryBackend()
            self.is_redis = False
            logger.info("ℹ️ GlobalCache initialized with MemoryBackend")

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def get_json(self, key: str) -> Optional[Any]:
        data = self.backend.get(self._k(key))
        if data:
            try:
                return json.loads(data)
            except Exception:
                return None
        return None

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None):
        try:
            self.backend.set(self._k(key), json.dumps(value), ttl)
        except Exception as e:
            logger.error(f"Cache SET failed for {key}: {e}")

    def delete(self, key: str):
        self.backend.delete(self._k(key))

class GlobalRateLimiter:
    """Shared rate limiter using Token Bucket algorithm in Redis."""
    def __init__(self, cache: GlobalCache):
        self.cache = cache

    def check(self, key: str, limit: float, burst: int) -> float:
        """
        Check if request is allowed.
        Returns: wait_time (0 if allowed)
        """
        if not self.cache.is_redis:
            # Memory fallback logic (simplified)
            return 0.0

        # Redis implementation of shared token bucket
        r = self.cache.backend.client
        k = self.cache._k(f"rate:{key}")
        
        now = time.time()
        
        # LUA script for atomic token bucket
        # Keys: [rate_key]
        # Args: [now, limit, burst]
        lua = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local limit = tonumber(ARGV[2])
        local burst = tonumber(ARGV[3])
        
        local data = redis.call('HMGET', key, 'tokens', 'last_ts')
        local tokens = tonumber(data[1]) or burst
        local last_ts = tonumber(data[2]) or now
        
        -- Regenerate
        local delta = math.max(0, now - last_ts)
        tokens = math.min(burst, tokens + delta * limit)
        
        local wait_time = 0
        if tokens < 1 then
            wait_time = (1 - tokens) / limit
        else
            tokens = tokens - 1
        end
        
        redis.call('HMSET', key, 'tokens', tokens, 'last_ts', now)
        redis.call('EXPIRE', key, 3600)
        
        return tostring(wait_time)
        """
        try:
            wait_time = float(r.eval(lua, 1, k, now, limit, burst))
            return wait_time
        except Exception as e:
            logger.error(f"Redis RateLimit error: {e}")
            return 0.0

# Singleton instances
global_cache = GlobalCache()
global_rate_limiter = GlobalRateLimiter(global_cache)

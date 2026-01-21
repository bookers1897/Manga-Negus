"""
================================================================================
MangaNegus v2.3 - Source Manager
================================================================================
Central manager for all manga source connectors.

THIS IS THE BRAIN OF THE MULTI-SOURCE SYSTEM:
  - Auto-discovers and loads all connectors in the sources/ directory
  - Manages shared HTTP session for all sources
  - Routes requests with automatic fallback when sources fail
  - Tracks health status of all sources
  - Provides unified API for the Flask app

HOW FALLBACK WORKS:
  1. User makes search request
  2. Manager tries active source first
  3. If it fails (rate limit, offline, etc.), tries next source
  4. Continues until success or all sources exhausted
  5. Failed sources get cooldown periods before retry
================================================================================
"""

import os
import sys
import importlib
import pkgutil
import threading
import time
from typing import List, Dict, Optional, Any, Callable
import requests
from cachetools import TTLCache

from .http_client import SmartSession

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)
from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerRegistry, CircuitBreakerConfig,
    CircuitState, CircuitOpenError
)

# Try to import Lua source discovery
try:
    from .lua_adapter import discover_lua_sources, LuaSourceAdapter
    HAS_LUA_SOURCES = True
except ImportError as e:
    HAS_LUA_SOURCES = False
    print(f"⚠️ Lua sources not available: {e}")

# Try to import WeebCentral V2 adapter (uses curl_cffi for Cloudflare bypass)
try:
    from .weebcentral_v2 import WeebCentralV2Connector
    HAS_WEEBCENTRAL_V2 = True
except ImportError as e:
    HAS_WEEBCENTRAL_V2 = False
    print(f"⚠️ WeebCentral V2 adapter not available: {e}")

# Try to import MangaSee V2 (curl_cffi)
try:
    from .mangasee_v2 import MangaSeeV2Connector
    HAS_MANGASEE_V2 = True
except ImportError as e:
    HAS_MANGASEE_V2 = False
    print(f"⚠️ MangaSee V2 adapter not available: {e}")

# Try to import MangaNato V2 (curl_cffi)
try:
    from .manganato_v2 import MangaNatoV2Connector
    HAS_MANGANATO_V2 = True
except ImportError as e:
    HAS_MANGANATO_V2 = False
    print(f"⚠️ MangaNato V2 adapter not available: {e}")

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass  # Already handled in app.py


class SourceManager:
    """
    Central manager for all manga source connectors.

    Usage:
        manager = SourceManager()
        results = manager.search("one piece")  # Uses active source with fallback

        manager.set_active_source("comick")  # Change preferred source

        # Get chapters from specific source
        chapters = manager.get_chapters("manga-id", "mangadex")

    ADVANCED FEATURES:
    - Adaptive priority: Sources are automatically ranked by health score
    - Health scoring: Tracks success rate, response time, and recent failures
    - Smart cooldowns: Failed sources get exponential backoff
    - Manga-source cache: Remembers which sources work for specific titles
    - Parallel search: Queries multiple sources concurrently for faster results
    """

    def __init__(self):
        """Initialize source manager."""
        # Registry of all loaded sources
        self._sources: Dict[str, BaseConnector] = {}

        # Shared HTTP session
        self._session: Optional[SmartSession] = None

        # Thread safety
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()

        # Active source preference
        self._active_source_id: Optional[str] = None

        # Base priority order for fallback (updated Jan 2026)
        # This is the starting order; adaptive scoring adjusts it dynamically
        self._priority_order = [
            "weebcentral-v2",   # HTMX breakthrough - 1170 chapters (needs curl_cffi)
            "mangafreak",       # Reliable backup with good chapter coverage
            "mangadex",         # Official API - fast and reliable
            "mangasee-v2",      # V2: Cloudflare bypass
            "manganato-v2",     # V2: Cloudflare bypass
            "mangafire",        # Cloudflare bypass - solid backup
            "comicx"            # Recent addition
            # Removed: annas-archive, libgen (never worked reliably)
        ]

        self._skipped_sources: list[dict[str, str]] = []

        # =========================================================================
        # CIRCUIT BREAKER (Reliability)
        # =========================================================================
        # Proper circuit breaker pattern: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
        # Prevents cascading failures and reduces load on failing sources
        self._circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=5,     # 5 consecutive failures to open circuit
            success_threshold=2,     # 2 successes in half-open to close
            recovery_timeout=60.0,   # 60 seconds before trying half-open
            half_open_max_calls=2    # Max 2 concurrent test calls in half-open
        )
        self._circuit_breakers = CircuitBreakerRegistry(self._circuit_breaker_config)

        # =========================================================================
        # ADAPTIVE SOURCE SCORING
        # =========================================================================
        # Health metrics per source: success rate, avg response time, last failure
        self._source_metrics: Dict[str, Dict[str, Any]] = {}

        # Manga-to-source cache: maps manga titles to known working sources
        # Format: {"naruto": {"source": "mangadex", "manga_id": "abc", "expires": timestamp}}
        self._manga_source_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 3600  # 1 hour cache TTL

        # Result caches (search/chapters/pages) for speed and resilience
        self._search_cache: Optional[TTLCache] = None
        self._popular_cache: Optional[TTLCache] = None
        self._latest_cache: Optional[TTLCache] = None
        self._chapters_cache: Optional[TTLCache] = None
        self._pages_cache: Optional[TTLCache] = None
        self._details_cache: Optional[TTLCache] = None

        # Cooldown settings for failed sources (used alongside circuit breaker)
        self._base_cooldown = 30  # 30 seconds base cooldown
        self._max_cooldown = 600  # 10 minutes max cooldown

        # Initialize
        self._create_session()
        self._discover_sources()
        self._apply_disabled_sources()
        self._init_source_metrics()
        self._init_result_caches()
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def _create_session(self) -> None:
        """Create shared requests session with connection pooling."""
        self._session = SmartSession(timeout=20)
        
        # Default headers
        self._session.headers.update({
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate"
        })
        
        # Connection pooling for performance
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=2
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def _init_result_caches(self) -> None:
        """Initialize result caches with environment-configurable TTLs."""
        self._search_cache = self._create_cache("SEARCH", ttl_default=300, max_default=512)
        self._popular_cache = self._create_cache("POPULAR", ttl_default=300, max_default=256)
        self._latest_cache = self._create_cache("LATEST", ttl_default=300, max_default=256)
        self._chapters_cache = self._create_cache("CHAPTERS", ttl_default=900, max_default=2048)
        self._pages_cache = self._create_cache("PAGES", ttl_default=300, max_default=4096)
        self._details_cache = self._create_cache("DETAILS", ttl_default=900, max_default=1024)

    def _create_cache(self, prefix: str, ttl_default: int, max_default: int) -> Optional[TTLCache]:
        ttl = int(os.environ.get(f"{prefix}_CACHE_TTL", str(ttl_default)))
        maxsize = int(os.environ.get(f"{prefix}_CACHE_MAX", str(max_default)))
        if ttl <= 0 or maxsize <= 0:
            return None
        return TTLCache(maxsize=maxsize, ttl=ttl)

    def _cache_get(self, cache: Optional[TTLCache], key: Any) -> Any:
        if cache is None:
            return None
        with self._cache_lock:
            return cache.get(key)

    def _cache_set(self, cache: Optional[TTLCache], key: Any, value: Any) -> None:
        if cache is None:
            return
        with self._cache_lock:
            cache[key] = value

    def _clear_result_caches(self) -> None:
        """Clear all result caches (search/popular/latest/chapters/pages/details)."""
        for cache in (
            self._search_cache,
            self._popular_cache,
            self._latest_cache,
            self._chapters_cache,
            self._pages_cache,
            self._details_cache
        ):
            if cache is not None:
                cache.clear()
    
    def _discover_sources(self) -> None:
        """
        Auto-discover and register all source connectors.
        
        Scans the sources/ directory for Python modules and instantiates
        any class that inherits from BaseConnector.
        
        This is how HakuNeko discovers its 730+ connectors!
        """
        sources_dir = os.path.dirname(__file__)
        
        # Classes to skip (adapters/factories that need constructor args)
        skip_classes = {'LuaSourceAdapter'}
        skip_playwright_modules = {'mangafire_v2'}
        skip_playwright = os.environ.get("SKIP_PLAYWRIGHT_SOURCES", "").lower() in {"1", "true", "yes", "on"}
        skip_discovery = os.environ.get("SKIP_SOURCE_DISCOVERY", "").lower() in {"1", "true", "yes", "on"}

        if skip_discovery:
            print("⚠️ Skipping source discovery (SKIP_SOURCE_DISCOVERY=1)")
            return

        for _, module_name, _ in pkgutil.iter_modules([sources_dir]):
            # Skip base module, __init__, and utility modules
            if module_name in ('base', '__init__', 'lua_runtime', 'async_base', 'async_utils'):
                continue
            if skip_playwright and module_name in skip_playwright_modules:
                print(f"⚠️ Skipping {module_name} (Playwright disabled via SKIP_PLAYWRIGHT_SOURCES)")
                self._skipped_sources.append({
                    "id": "mangafire-v2",
                    "name": "MangaFire V2",
                    "icon": "🔥",
                    "reason": "playwright_disabled"
                })
                continue

            try:
                # Import the module
                module = importlib.import_module(f'.{module_name}', 'sources')

                # Find connector classes
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    # Check if it's a BaseConnector subclass
                    if (isinstance(attr, type) and
                        issubclass(attr, BaseConnector) and
                        attr is not BaseConnector and
                        attr.__name__ not in skip_classes):

                        # Instantiate and register
                        connector = attr()
                        connector.session = self._session
                        self._sources[connector.id] = connector

            except Exception as e:
                print(f"⚠️ Failed to load source '{module_name}': {e}")

        # Discover Lua sources (FMD-compatible modules)
        if HAS_LUA_SOURCES:
            try:
                lua_sources = discover_lua_sources()
                for adapter in lua_sources:
                    adapter.session = self._session
                    self._sources[adapter.id] = adapter
                    print(f"✨ Loaded Lua source: {adapter.name}")
            except Exception as e:
                print(f"⚠️ Failed to load Lua sources: {e}")

        # Also register our built-in MangaDex Lua adapter (uses direct API)
        if HAS_LUA_SOURCES and 'lua-mangadex' not in self._sources:
            try:
                adapter = LuaSourceAdapter('MangaDex')
                adapter.session = self._session
                self._sources[adapter.id] = adapter
                print(f"✨ Loaded MangaDex Lua adapter")
            except Exception as e:
                print(f"⚠️ Failed to load MangaDex Lua adapter: {e}")

        # Register WeebCentral V2 adapter (uses curl_cffi for Cloudflare bypass)
        if HAS_WEEBCENTRAL_V2 and 'weebcentral-v2' not in self._sources:
            try:
                adapter = WeebCentralV2Connector()
                self._sources[adapter.id] = adapter
                print(f"✨ Loaded WeebCentral V2 adapter (Cloudflare bypass)")
            except Exception as e:
                print(f"⚠️ Failed to load WeebCentral V2 adapter: {e}")

        # Register MangaSee V2 (curl_cffi)
        if HAS_MANGASEE_V2 and 'mangasee-v2' not in self._sources:
            try:
                adapter = MangaSeeV2Connector()
                self._sources[adapter.id] = adapter
                print(f"✨ Loaded MangaSee V2 adapter (Cloudflare bypass)")
            except Exception as e:
                print(f"⚠️ Failed to load MangaSee V2 adapter: {e}")

        # Register MangaNato V2 (curl_cffi)
        if HAS_MANGANATO_V2 and 'manganato-v2' not in self._sources:
            try:
                adapter = MangaNatoV2Connector()
                self._sources[adapter.id] = adapter
                print(f"✨ Loaded MangaNato V2 adapter (Cloudflare bypass)")
            except Exception as e:
                print(f"⚠️ Failed to load MangaNato V2 adapter: {e}")

        # Set default active source
        if self._sources:
            # Use priority order (WeebCentral Lua first, then MangaDex, etc.)
            for preferred in self._priority_order:
                if preferred in self._sources:
                    self._active_source_id = preferred
                    break

            # Fallback to first available
            if not self._active_source_id:
                self._active_source_id = list(self._sources.keys())[0]

    def _apply_disabled_sources(self) -> None:
        """Remove disabled sources from the registry based on env var."""
        raw = os.environ.get("DISABLED_SOURCES", "")
        if not raw:
            return
        disabled = {item.strip() for item in raw.split(",") if item.strip()}
        for source_id in list(self._sources.keys()):
            if source_id in disabled:
                self._sources.pop(source_id, None)
                self._skipped_sources.append({
                    "source": source_id,
                    "reason": "disabled"
                })

    def _init_source_metrics(self) -> None:
        """Initialize health metrics for all sources."""
        for source_id in self._sources:
            self._source_metrics[source_id] = {
                'successes': 0,
                'failures': 0,
                'total_requests': 0,
                'total_response_time': 0.0,
                'last_failure_time': 0,
                'consecutive_failures': 0,
                'cooldown_until': 0,
                'health_score': 100.0  # Start with perfect health
            }

    def _get_health_score(self, source_id: str) -> float:
        """
        Calculate dynamic health score for a source (0-100).

        Factors:
        - Success rate (60% weight)
        - Recent failures penalty (25% weight)
        - Response time penalty (15% weight)
        """
        metrics = self._source_metrics.get(source_id, {})
        if not metrics or metrics.get('total_requests', 0) == 0:
            return 100.0  # New source, give it a chance

        total = metrics['total_requests']
        successes = metrics['successes']
        failures = metrics['failures']
        consecutive_failures = metrics['consecutive_failures']

        # Success rate component (60% weight)
        success_rate = (successes / total) * 100 if total > 0 else 100
        success_component = success_rate * 0.6

        # Recent failures penalty (25% weight) - exponential penalty for consecutive failures
        failure_penalty = min(25, consecutive_failures * 5)
        failure_component = 25 - failure_penalty

        # Response time component (15% weight) - penalize slow sources
        avg_response_time = metrics['total_response_time'] / total if total > 0 else 0
        # 0-1s = full points, 1-5s = partial, >5s = 0
        if avg_response_time <= 1.0:
            time_component = 15
        elif avg_response_time <= 5.0:
            time_component = 15 * (1 - (avg_response_time - 1) / 4)
        else:
            time_component = 0

        return max(0, success_component + failure_component + time_component)

    def _record_success(self, source_id: str, response_time: float) -> None:
        """Record a successful request for a source."""
        with self._lock:
            if source_id not in self._source_metrics:
                self._init_source_metrics()

            metrics = self._source_metrics[source_id]
            metrics['successes'] += 1
            metrics['total_requests'] += 1
            metrics['total_response_time'] += response_time
            metrics['consecutive_failures'] = 0
            metrics['health_score'] = self._get_health_score(source_id)

    def _record_failure(self, source_id: str) -> None:
        """Record a failed request and apply cooldown if needed."""
        with self._lock:
            if source_id not in self._source_metrics:
                self._init_source_metrics()

            metrics = self._source_metrics[source_id]
            metrics['failures'] += 1
            metrics['total_requests'] += 1
            metrics['consecutive_failures'] += 1
            metrics['last_failure_time'] = time.time()

            # Apply exponential backoff cooldown
            consecutive = metrics['consecutive_failures']
            cooldown = min(self._base_cooldown * (2 ** (consecutive - 1)), self._max_cooldown)
            metrics['cooldown_until'] = time.time() + cooldown
            metrics['health_score'] = self._get_health_score(source_id)

            self._log(f"⏳ {source_id} cooldown for {cooldown:.0f}s (failures: {consecutive})")

    def _is_source_on_cooldown(self, source_id: str) -> bool:
        """Check if a source is currently on cooldown."""
        metrics = self._source_metrics.get(source_id, {})
        cooldown_until = metrics.get('cooldown_until', 0)
        return time.time() < cooldown_until

    def _cache_manga_source(self, title: str, source_id: str, manga_id: str) -> None:
        """Cache which source works for a manga title."""
        normalized_title = title.lower().strip()
        self._manga_source_cache[normalized_title] = {
            'source': source_id,
            'manga_id': manga_id,
            'expires': time.time() + self._cache_ttl
        }

    def _get_cached_source(self, title: str) -> Optional[Dict[str, str]]:
        """Get cached source for a manga title if available and not expired."""
        normalized_title = title.lower().strip()
        cached = self._manga_source_cache.get(normalized_title)
        if cached and time.time() < cached['expires']:
            return {'source_id': cached['source'], 'manga_id': cached['manga_id']}
        return None
    
    # =========================================================================
    # SOURCE ACCESS
    # =========================================================================
    
    @property
    def sources(self) -> Dict[str, BaseConnector]:
        """Get all registered sources."""
        return self._sources
    
    @property
    def active_source(self) -> Optional[BaseConnector]:
        """Get currently active source."""
        if self._active_source_id:
            return self._sources.get(self._active_source_id)
        return None
    
    @property
    def active_source_id(self) -> Optional[str]:
        """Get ID of active source."""
        return self._active_source_id
    
    def set_active_source(self, source_id: str) -> bool:
        """
        Set the active source.
        
        Returns True if successful, False if source doesn't exist.
        """
        if source_id in self._sources:
            self._active_source_id = source_id
            return True
        return False
    
    def get_source(self, source_id: str) -> Optional[BaseConnector]:
        """Get a specific source by ID."""
        return self._sources.get(source_id)
    
    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Get list of all sources with status info."""
        return [
            {
                "id": source.id,
                "name": source.name,
                "icon": source.icon,
                "status": source.status.value,
                "is_available": source.is_available,
                "is_active": source.id == self._active_source_id,
                "features": {
                    "popular": source.supports_popular,
                    "latest": source.supports_latest,
                    "cloudflare": source.requires_cloudflare
                }
            }
            for source in self._sources.values()
        ]
    
    # =========================================================================
    # FALLBACK LOGIC (ADAPTIVE)
    # =========================================================================

    def _get_ordered_sources(self, skip_cooldown: bool = False, skip_circuit_breaker: bool = False) -> List[BaseConnector]:
        """
        Get sources ordered by adaptive health score, respecting circuit breakers.

        The order is determined by:
          1. Active source (if available, healthy, and circuit not open)
          2. Sources sorted by health score (highest first)
          3. Sources with open circuits are skipped unless skip_circuit_breaker=True
          4. Sources on cooldown are skipped unless skip_cooldown=True

        Args:
            skip_cooldown: If True, include sources even if on cooldown
            skip_circuit_breaker: If True, include sources even if circuit is open
        """
        ordered = []
        seen = set()

        def is_source_available(source_id: str) -> bool:
            """Check if source is available (circuit closed or half-open)."""
            breaker = self._circuit_breakers.get(source_id)
            if breaker and breaker.is_open and not skip_circuit_breaker:
                return False
            if not skip_cooldown and self._is_source_on_cooldown(source_id):
                return False
            return True

        # Active source first (if healthy and circuit not open)
        if self._active_source_id:
            source = self._sources.get(self._active_source_id)
            if source and source.is_available and is_source_available(source.id):
                ordered.append(source)
                seen.add(source.id)

        # Build list of remaining sources with their health scores
        scored_sources = []
        for source_id, source in self._sources.items():
            if source_id in seen or not source.is_available:
                continue
            if not is_source_available(source_id):
                continue

            health = self._source_metrics.get(source_id, {}).get('health_score', 100.0)

            # Boost priority sources slightly
            if source_id in self._priority_order:
                priority_bonus = (len(self._priority_order) - self._priority_order.index(source_id)) * 2
                health = min(100, health + priority_bonus)

            # Penalize sources with half-open circuits (they're recovering)
            breaker = self._circuit_breakers.get(source_id)
            if breaker and breaker.state == CircuitState.HALF_OPEN:
                health = max(0, health - 20)

            scored_sources.append((source, health))

        # Sort by health score (highest first)
        scored_sources.sort(key=lambda x: x[1], reverse=True)

        for source, _ in scored_sources:
            ordered.append(source)

        return ordered

    def _with_fallback(
        self,
        operation: Callable[[BaseConnector], Any],
        operation_name: str = "operation"
    ) -> Any:
        """
        Execute an operation with circuit breaker and automatic fallback.

        Flow:
        1. Get sources ordered by health score, excluding open circuits
        2. For each source, check circuit breaker state
        3. If circuit allows, execute operation
        4. Record success/failure to circuit breaker
        5. Fallback to next source on failure

        Args:
            operation: Function that takes a source and returns result
            operation_name: Name for logging

        Returns:
            Result from first successful source, or None/empty
        """
        sources = self._get_ordered_sources()

        if not sources:
            # If all sources have open circuits or cooldowns, try anyway
            sources = self._get_ordered_sources(skip_cooldown=True, skip_circuit_breaker=True)
            if not sources:
                self._log("❌ No available sources!")
                return None
            self._log("⚠️ All sources unavailable (circuit open or cooldown), trying anyway...")

        for source in sources:
            # Get or create circuit breaker for this source
            breaker = self._circuit_breakers.get_or_create(source.id)

            # Check if circuit allows this request
            if not breaker.can_execute():
                self._log(f"🔴 Circuit OPEN for {source.name}, skipping (retry in {breaker.retry_after:.0f}s)")
                breaker.record_rejection()
                continue

            start_time = time.time()
            try:
                result = operation(source)
                response_time = time.time() - start_time

                # Check if result has actual data
                if result is not None and result:
                    # Success! Record to both circuit breaker and health metrics
                    breaker.record_success()
                    self._record_success(source.id, response_time)

                    # Log circuit state if recovering
                    if breaker.state == CircuitState.HALF_OPEN:
                        self._log(f"🟡 {source.name} recovering (half-open)")
                    elif breaker.stats.consecutive_successes == self._circuit_breaker_config.success_threshold:
                        self._log(f"🟢 {source.name} circuit CLOSED (recovered)")

                    return result

                # Empty result - don't penalize circuit but don't reward either
                # (source works but doesn't have this manga)

            except Exception as e:
                # Failure! Record to circuit breaker and health metrics
                breaker.record_failure()
                self._record_failure(source.id)

                # Log circuit state change
                if breaker.is_open:
                    self._log(f"🔴 Circuit OPENED for {source.name} (too many failures)")
                else:
                    self._log(f"⚠️ {source.name} failed: {e}")

                try:
                    source._handle_error(str(e))
                except Exception:
                    pass
                continue

        self._log(f"❌ All sources failed for {operation_name}")
        return None

    def _parallel_search(self, query: str, page: int = 1, max_workers: int = 3) -> List[MangaResult]:
        """
        Search multiple sources in parallel for faster results.

        Args:
            query: Search term
            page: Page number
            max_workers: Max concurrent source queries

        Returns:
            Combined and deduplicated results from all successful sources
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sources = self._get_ordered_sources()[:max_workers]
        if not sources:
            return []

        results_map: Dict[str, MangaResult] = {}  # Dedupe by title
        results_list: List[MangaResult] = []

        def search_source(source: BaseConnector) -> tuple:
            start_time = time.time()
            try:
                results = source.search(query, page)
                response_time = time.time() - start_time
                return (source.id, results, response_time, None)
            except Exception as e:
                return (source.id, [], 0, str(e))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(search_source, s): s for s in sources}

            for future in as_completed(futures, timeout=15):
                source_id, results, response_time, error = future.result()

                if error:
                    self._record_failure(source_id)
                    self._log(f"⚠️ Parallel search failed for {source_id}: {error}")
                elif results:
                    self._record_success(source_id, response_time)
                    # Add results, deduplicating by title
                    for manga in results:
                        title_key = manga.title.lower().strip()
                        if title_key not in results_map:
                            results_map[title_key] = manga
                            results_list.append(manga)
                        # Cache this manga-source mapping
                        self._cache_manga_source(manga.title, source_id, manga.id)

        return results_list
    
    def _log(self, msg: str) -> None:
        """Log a message."""
        from sources.base import source_log
        source_log(msg)

    
    # =========================================================================
    # URL DETECTION
    # =========================================================================
    
    def detect_source_from_url(self, url: str) -> Optional[Dict[str, str]]:
        """
        Detect which source a manga URL belongs to and extract the manga ID.
        
        Args:
            url: Full manga URL (e.g., "https://mangadex.org/title/abc-123")
            
        Returns:
            Dict with keys: {source_id, manga_id, source_name} or None
            
        Example:
            >>> manager.detect_source_from_url("https://mangadex.org/title/abc-123")
            {'source_id': 'mangadex', 'manga_id': 'abc-123', 'source_name': 'MangaDex'}
        """
        for source_id, source in self._sources.items():
            if source.matches_url(url):
                manga_id = source.extract_id_from_url(url)
                if manga_id:
                    return {
                        'source_id': source_id,
                        'manga_id': manga_id,
                        'source_name': source.name
                    }
        
        self._log(f"❌ Could not detect source for URL: {url}")
        return None
    
    
    # =========================================================================
    # PUBLIC API (with fallback)
    # =========================================================================
    
    def search(
        self,
        query: str,
        source_id: Optional[str] = None,
        page: int = 1
    ) -> List[MangaResult]:
        """
        Search for manga.
        
        Args:
            query: Search term
            source_id: Specific source (None = active with fallback)
            page: Page number
        """
        # Use specific source if requested
        if source_id:
            cache_key = ("search", source_id, query.lower().strip(), page)
            cached = self._cache_get(self._search_cache, cache_key)
            if cached is not None:
                return cached
            source = self._sources.get(source_id)
            if source:
                results = source.search(query, page)
                self._cache_set(self._search_cache, cache_key, results)
                return results
            return []

        # Use fallback
        cache_key = ("search", "*", query.lower().strip(), page)
        cached = self._cache_get(self._search_cache, cache_key)
        if cached is not None:
            return cached

        def search_op(source: BaseConnector):
            return source.search(query, page)

        results = self._with_fallback(search_op, f"search: {query}") or []
        if results:
            self._cache_set(self._search_cache, cache_key, results)
        return results
    
    def get_popular(
        self,
        source_id: Optional[str] = None,
        page: int = 1
    ) -> List[MangaResult]:
        """Get popular manga with fallback."""
        if source_id:
            cache_key = ("popular", source_id, page)
            cached = self._cache_get(self._popular_cache, cache_key)
            if cached is not None:
                return cached
            source = self._sources.get(source_id)
            if source and source.supports_popular:
                results = source.get_popular(page)
                if results:
                    self._cache_set(self._popular_cache, cache_key, results)
                return results
            return []

        cache_key = ("popular", "*", page)
        cached = self._cache_get(self._popular_cache, cache_key)
        if cached is not None:
            return cached
        
        def popular_op(source: BaseConnector):
            if source.supports_popular:
                return source.get_popular(page)
            return None

        results = self._with_fallback(popular_op, "get_popular") or []
        if results:
            self._cache_set(self._popular_cache, cache_key, results)
        return results
    
    def get_latest(
        self,
        source_id: Optional[str] = None,
        page: int = 1
    ) -> List[MangaResult]:
        """Get latest updates with fallback."""
        if source_id:
            cache_key = ("latest", source_id, page)
            cached = self._cache_get(self._latest_cache, cache_key)
            if cached is not None:
                return cached
            source = self._sources.get(source_id)
            if source and source.supports_latest:
                results = source.get_latest(page)
                if results:
                    self._cache_set(self._latest_cache, cache_key, results)
                return results
            return []

        cache_key = ("latest", "*", page)
        cached = self._cache_get(self._latest_cache, cache_key)
        if cached is not None:
            return cached
        
        def latest_op(source: BaseConnector):
            if source.supports_latest:
                return source.get_latest(page)
            return None

        results = self._with_fallback(latest_op, "get_latest") or []
        if results:
            self._cache_set(self._latest_cache, cache_key, results)
        return results
    
    def get_chapters(
        self,
        manga_id: str,
        source_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get chapters for a manga.
        
        Note: source_id is REQUIRED because manga_id is source-specific.
        """
        source = self._sources.get(source_id)
        if not source:
            self._log(f"❌ Source '{source_id}' not found")
            return []

        cache_key = ("chapters", source_id, manga_id, language)
        cached = self._cache_get(self._chapters_cache, cache_key)
        if cached is not None:
            return cached

        chapters = source.get_chapters(manga_id, language)
        if chapters:
            self._cache_set(self._chapters_cache, cache_key, chapters)
        return chapters
    
    def get_pages(
        self,
        chapter_id: str,
        source_id: str
    ) -> List[PageResult]:
        """
        Get page images for a chapter.
        
        Note: source_id is REQUIRED because chapter_id is source-specific.
        """
        source = self._sources.get(source_id)
        if not source:
            return []

        cache_key = ("pages", source_id, chapter_id)
        cached = self._cache_get(self._pages_cache, cache_key)
        if cached is not None:
            return cached

        pages = source.get_pages(chapter_id)
        if pages:
            self._cache_set(self._pages_cache, cache_key, pages)
        return pages
    
    def get_manga_details(
        self,
        manga_id: str,
        source_id: str
    ) -> Optional[MangaResult]:
        """Get detailed manga info."""
        source = self._sources.get(source_id)
        if not source:
            return None

        cache_key = ("details", source_id, manga_id)
        cached = self._cache_get(self._details_cache, cache_key)
        if cached is not None:
            return cached

        details = source.get_manga_details(manga_id)
        if details:
            self._cache_set(self._details_cache, cache_key, details)
        return details
    
    # =========================================================================
    # HEALTH & STATUS
    # =========================================================================
    
    def list_sources(self) -> List[BaseConnector]:
        """Get list of all source connectors."""
        return list(self._sources.values())

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health status of all sources with circuit breaker and adaptive metrics."""
        source_reports = []
        for source in self._sources.values():
            base_info = source.get_health_info()
            metrics = self._source_metrics.get(source.id, {})

            # Get circuit breaker status
            breaker = self._circuit_breakers.get(source.id)
            circuit_state = breaker.state.value if breaker else "unknown"
            circuit_retry_after = breaker.retry_after if breaker else 0

            # Add adaptive scoring and circuit breaker metrics
            base_info.update({
                'health_score': metrics.get('health_score', 100.0),
                'success_rate': (
                    (metrics.get('successes', 0) / metrics.get('total_requests', 1) * 100)
                    if metrics.get('total_requests', 0) > 0 else 100.0
                ),
                'total_requests': metrics.get('total_requests', 0),
                'consecutive_failures': metrics.get('consecutive_failures', 0),
                'on_cooldown': self._is_source_on_cooldown(source.id),
                'cooldown_remaining': max(0, metrics.get('cooldown_until', 0) - time.time()),
                # Circuit breaker info
                'circuit_state': circuit_state,
                'circuit_retry_after': round(circuit_retry_after, 1)
            })
            source_reports.append(base_info)

        # Sort by health score for visibility
        source_reports.sort(key=lambda x: x.get('health_score', 0), reverse=True)

        # Get circuit breaker summary
        cb_status = self._circuit_breakers.get_all_status()

        return {
            "active_source": self._active_source_id,
            "sources": source_reports,
            "skipped": self._skipped_sources,
            "available_count": sum(1 for s in self._sources.values() if s.is_available),
            "healthy_count": sum(1 for s in self._sources.values() if not self._is_source_on_cooldown(s.id)),
            "total_count": len(self._sources),
            "cache_size": len(self._manga_source_cache),
            "result_cache_sizes": {
                "search": len(self._search_cache) if self._search_cache else 0,
                "popular": len(self._popular_cache) if self._popular_cache else 0,
                "latest": len(self._latest_cache) if self._latest_cache else 0,
                "chapters": len(self._chapters_cache) if self._chapters_cache else 0,
                "pages": len(self._pages_cache) if self._pages_cache else 0,
                "details": len(self._details_cache) if self._details_cache else 0
            },
            # Circuit breaker summary
            "circuit_breakers": {
                "open_count": cb_status.get("open_count", 0),
                "half_open_count": cb_status.get("half_open_count", 0),
                "closed_count": cb_status.get("closed_count", 0)
            }
        }
    
    def reset_source(self, source_id: str) -> bool:
        """Reset a source's error state, metrics, and circuit breaker."""
        source = self._sources.get(source_id)
        if source:
            source.reset()
            # Reset circuit breaker
            self._circuit_breakers.reset(source_id)
            # Reset adaptive metrics
            if source_id in self._source_metrics:
                self._source_metrics[source_id] = {
                    'successes': 0,
                    'failures': 0,
                    'total_requests': 0,
                    'total_response_time': 0.0,
                    'last_failure_time': 0,
                    'consecutive_failures': 0,
                    'cooldown_until': 0,
                    'health_score': 100.0
                }
            self._clear_result_caches()
            self._log(f"🔄 Reset source: {source.name} (circuit breaker closed)")
            return True
        return False

    def reset_all_sources(self) -> None:
        """Reset all sources, metrics, and circuit breakers."""
        for source in self._sources.values():
            source.reset()
        # Reset all circuit breakers
        self._circuit_breakers.reset_all()
        # Reinitialize all metrics
        self._init_source_metrics()
        # Clear manga-source cache
        self._manga_source_cache.clear()
        self._clear_result_caches()
        self._log("🔄 Reset all sources and circuit breakers")


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_manager: Optional[SourceManager] = None
_manager_lock = threading.Lock()


def get_source_manager() -> SourceManager:
    """Get or create the global SourceManager instance."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = SourceManager()
    return _manager

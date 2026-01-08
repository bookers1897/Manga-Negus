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

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
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
    """
    
    def __init__(self):
        """Initialize source manager."""
        # Registry of all loaded sources
        self._sources: Dict[str, BaseConnector] = {}
        
        # Shared HTTP session
        self._session: Optional[requests.Session] = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Active source preference
        self._active_source_id: Optional[str] = None
        
        # Priority order for fallback (updated Jan 2026)
        # MangaDex first for fast searches (0.65s avg)
        # weebcentral-v2 moved down - requires: pip install curl_cffi
        self._priority_order = [
            "weebcentral-v2",   # HTMX breakthrough - 1170 chapters (needs curl_cffi)
            "mangasee-v2",      # V2: Cloudflare bypass
            "manganato-v2",     # V2: Cloudflare bypass
            "mangadex",         # Official API - fast and reliable (default for search)
            "mangafire",        # Cloudflare bypass - solid backup
            "annas-archive",    # Shadow library aggregator - complete volumes
            "libgen",           # Library Genesis direct - 95TB+ comics
            "comicx"            # Recent addition
        ]
        
        # Initialize
        self._create_session()
        self._discover_sources()
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def _create_session(self) -> None:
        """Create shared requests session with connection pooling."""
        self._session = requests.Session()
        
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

        for _, module_name, _ in pkgutil.iter_modules([sources_dir]):
            # Skip base module, __init__, and utility modules
            if module_name in ('base', '__init__', 'lua_runtime', 'async_base', 'async_utils'):
                continue

            if skip_playwright and module_name in skip_playwright_modules:
                print(f"⚠️ Skipping {module_name} (Playwright disabled via SKIP_PLAYWRIGHT_SOURCES)")
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
    # FALLBACK LOGIC
    # =========================================================================
    
    def _get_ordered_sources(self) -> List[BaseConnector]:
        """
        Get sources ordered by priority for fallback.
        
        Order:
          1. Active source (if available)
          2. Sources in priority_order
          3. Remaining sources
        """
        ordered = []
        seen = set()
        
        # Active source first
        if self._active_source_id:
            source = self._sources.get(self._active_source_id)
            if source and source.is_available:
                ordered.append(source)
                seen.add(source.id)
        
        # Priority sources
        for source_id in self._priority_order:
            if source_id not in seen and source_id in self._sources:
                source = self._sources[source_id]
                if source.is_available:
                    ordered.append(source)
                    seen.add(source_id)
        
        # Remaining sources
        for source_id, source in self._sources.items():
            if source_id not in seen and source.is_available:
                ordered.append(source)
        
        return ordered
    
    def _with_fallback(
        self,
        operation: Callable[[BaseConnector], Any],
        operation_name: str = "operation"
    ) -> Any:
        """
        Execute an operation with automatic fallback.
        
        Tries each available source in order until one succeeds.
        
        Args:
            operation: Function that takes a source and returns result
            operation_name: Name for logging
            
        Returns:
            Result from first successful source, or None/empty
        """
        sources = self._get_ordered_sources()
        
        if not sources:
            self._log("❌ No available sources!")
            return None
        
        for source in sources:
            try:
                result = operation(source)

                # THE FIX: Only check for None, not empty list
                # An empty list [] means "successfully searched, but no results found"
                # None means "technical failure" (network error, etc.)
                if result is not None:
                    return result

            except Exception as e:
                try:
                    source._handle_error(str(e))
                except Exception:
                    pass
                self._log(f"⚠️ {source.name} failed: {e}")
                continue

        self._log(f"❌ All sources failed for {operation_name}")
        return None
    
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
            source = self._sources.get(source_id)
            if source:
                return source.search(query, page)
            return []
        
        # Use fallback
        def search_op(source: BaseConnector):
            return source.search(query, page)
        
        return self._with_fallback(search_op, f"search: {query}") or []
    
    def get_popular(
        self,
        source_id: Optional[str] = None,
        page: int = 1
    ) -> List[MangaResult]:
        """Get popular manga with fallback."""
        if source_id:
            source = self._sources.get(source_id)
            if source and source.supports_popular:
                return source.get_popular(page)
            return []
        
        def popular_op(source: BaseConnector):
            if source.supports_popular:
                return source.get_popular(page)
            return None
        
        return self._with_fallback(popular_op, "get_popular") or []
    
    def get_latest(
        self,
        source_id: Optional[str] = None,
        page: int = 1
    ) -> List[MangaResult]:
        """Get latest updates with fallback."""
        if source_id:
            source = self._sources.get(source_id)
            if source and source.supports_latest:
                return source.get_latest(page)
            return []
        
        def latest_op(source: BaseConnector):
            if source.supports_latest:
                return source.get_latest(page)
            return None
        
        return self._with_fallback(latest_op, "get_latest") or []
    
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
        
        return source.get_chapters(manga_id, language)
    
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
        
        return source.get_pages(chapter_id)
    
    def get_manga_details(
        self,
        manga_id: str,
        source_id: str
    ) -> Optional[MangaResult]:
        """Get detailed manga info."""
        source = self._sources.get(source_id)
        if not source:
            return None
        
        return source.get_manga_details(manga_id)
    
    # =========================================================================
    # HEALTH & STATUS
    # =========================================================================
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get health status of all sources."""
        return {
            "active_source": self._active_source_id,
            "sources": [s.get_health_info() for s in self._sources.values()],
            "available_count": sum(1 for s in self._sources.values() if s.is_available),
            "total_count": len(self._sources)
        }
    
    def reset_source(self, source_id: str) -> bool:
        """Reset a source's error state."""
        source = self._sources.get(source_id)
        if source:
            source.reset()
            return True
        return False
    
    def reset_all_sources(self) -> None:
        """Reset all sources."""
        for source in self._sources.values():
            source.reset()


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

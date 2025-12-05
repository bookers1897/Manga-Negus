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
        
        # Priority order for fallback (updated for 2025)
        # ComicK and MangaNato are more reliable and have less strict rate limits
        self._priority_order = ["comick", "mangadex", "manganato", "mangafire", "mangahere", "mangakakalot", "mangasee"]
        
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
            "Accept-Encoding": "gzip, deflate, br"
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
        
        for _, module_name, _ in pkgutil.iter_modules([sources_dir]):
            # Skip base module and __init__
            if module_name in ('base', '__init__'):
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
                        attr is not BaseConnector):
                        
                        # Instantiate and register
                        connector = attr()
                        connector.session = self._session
                        self._sources[connector.id] = connector
                        
            except Exception as e:
                print(f"⚠️ Failed to load source '{module_name}': {e}")
        
        # Set default active source
        if self._sources:
            # Prefer ComicK (more lenient), then MangaDex
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
                
                # Check if we got valid results
                if result is not None and result != []:
                    return result
                
            except Exception as e:
                self._log(f"⚠️ {source.name} failed: {e}")
                continue
        
        self._log(f"❌ All sources failed for {operation_name}")
        return None
    
    def _log(self, msg: str) -> None:
        """Log a message."""
        from sources.base import source_log
        source_log(msg)
    
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


def get_source_manager() -> SourceManager:
    """Get or create the global SourceManager instance."""
    global _manager
    if _manager is None:
        _manager = SourceManager()
    return _manager

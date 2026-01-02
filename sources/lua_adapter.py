"""
================================================================================
MangaNegus v3.0 - Lua Source Adapter
================================================================================
Adapter that wraps Lua modules to work with the BaseConnector system.

This allows FMD's 590+ Lua modules to integrate seamlessly with
MangaNegus's existing source architecture.

Usage:
    adapter = LuaSourceAdapter("MangaDex", session)
    results = adapter.search("one piece")
    chapters = adapter.get_chapters(manga_id)
================================================================================
"""

import os
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .base import (
    BaseConnector,
    MangaResult,
    ChapterResult,
    PageResult,
    SourceStatus,
    source_log
)
from .lua_runtime import LuaRuntime, LuaModuleLoader


# =============================================================================
# LUA SOURCE ADAPTER
# =============================================================================

class LuaSourceAdapter(BaseConnector):
    """
    Adapter that wraps a Lua module to implement BaseConnector.

    This bridges FMD's Lua modules with MangaNegus's source system.
    """

    # Base directory for Lua modules
    LUA_MODULES_DIR = os.path.join(os.path.dirname(__file__), "lua", "modules")

    def __init__(self, module_name: str):
        """
        Initialize adapter for a specific Lua module.

        Args:
            module_name: Name of the Lua module (without .lua extension)
        """
        super().__init__()

        self.module_name = module_name
        self._runtime: Optional[LuaRuntime] = None
        self._module_info: Optional[Dict[str, Any]] = None

        # Will be set after loading
        self.id = f"lua-{module_name.lower()}"
        self.name = f"{module_name} (Lua)"
        self.icon = "📜"

        # Try to load the module
        self._load_module()

    def _load_module(self) -> bool:
        """Load and initialize the Lua module."""
        try:
            self._runtime = LuaRuntime(self.session)

            module_path = os.path.join(self.LUA_MODULES_DIR, f"{self.module_name}.lua")
            if not os.path.exists(module_path):
                source_log(f"[{self.id}] Module not found: {module_path}")
                return False

            # Execute the module file
            if not self._runtime.execute_file(module_path):
                source_log(f"[{self.id}] Failed to execute module")
                return False

            # Call Init() to register the module
            self._runtime.call_function("Init")

            # Get module info
            module = self._runtime.get_module()
            if module:
                self.name = f"{module.Name} (Lua)"
                self.base_url = module.RootURL
                self._module_info = {
                    "id": module.ID,
                    "name": module.Name,
                    "root_url": module.RootURL,
                    "category": module.Category,
                    "get_info": module.OnGetInfo,
                    "get_pages": module.OnGetPageNumber,
                }
                source_log(f"[{self.id}] Loaded: {module.Name}")
                return True

            return False
        except Exception as e:
            source_log(f"[{self.id}] Error loading module: {e}")
            return False

    def _ensure_runtime(self) -> bool:
        """Ensure runtime is loaded."""
        if self._runtime is None:
            return self._load_module()
        return True

    # =========================================================================
    # BASECONNECTOR IMPLEMENTATION
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search for manga using the Lua module.

        For FMD modules, we typically need to:
        1. Build a search URL
        2. Call GetNameAndLink or a custom search function
        3. Parse the results from LINKS/NAMES lists
        """
        if not self._ensure_runtime():
            return []

        self._wait_for_rate_limit()

        try:
            # For most FMD modules, search is done via API
            # We'll implement a simplified approach using the API directly
            source_log(f"[{self.id}] Searching: {query}")

            # Clear previous results
            self._runtime.reset_lists()

            # Build search URL based on module type
            if "mangadex" in self.module_name.lower():
                return self._search_mangadex(query, page)
            else:
                # Generic search - try the module's method
                return self._search_generic(query, page)

        except Exception as e:
            self._handle_error(str(e))
            source_log(f"[{self.id}] Search error: {e}")
            return []

    def _search_mangadex(self, query: str, page: int = 1) -> List[MangaResult]:
        """MangaDex-specific search using their API."""
        limit = 15
        offset = (page - 1) * limit

        url = f"https://api.mangadex.org/manga?title={query}&limit={limit}&offset={offset}&includes[]=cover_art&includes[]=author"

        if self._runtime.HTTP.GET(url):
            doc = self._runtime.HTTP.Document.ToString()
            return self._parse_mangadex_search(doc)

        return []

    def _parse_mangadex_search(self, json_str: str) -> List[MangaResult]:
        """Parse MangaDex API search results."""
        import json

        try:
            data = json.loads(json_str)
            results = []

            for manga in data.get("data", []):
                attrs = manga.get("attributes", {})

                # Get English title
                title = ""
                titles = attrs.get("title", {})
                if "en" in titles:
                    title = titles["en"]
                elif titles:
                    title = next(iter(titles.values()), "")

                # Get cover
                cover_url = None
                for rel in manga.get("relationships", []):
                    if rel.get("type") == "cover_art":
                        filename = rel.get("attributes", {}).get("fileName")
                        if filename:
                            cover_url = f"https://uploads.mangadex.org/covers/{manga['id']}/{filename}.256.jpg"
                            break

                # Get author
                author = None
                for rel in manga.get("relationships", []):
                    if rel.get("type") == "author":
                        author = rel.get("attributes", {}).get("name")
                        break

                results.append(MangaResult(
                    id=manga["id"],
                    title=title,
                    source=self.id,
                    cover_url=cover_url,
                    description=attrs.get("description", {}).get("en"),
                    author=author,
                    status=attrs.get("status"),
                    url=f"https://mangadex.org/title/{manga['id']}",
                    genres=[tag["attributes"]["name"]["en"] for tag in attrs.get("tags", []) if "name" in tag.get("attributes", {})],
                    year=attrs.get("year")
                ))

            self._handle_success()
            return results

        except Exception as e:
            source_log(f"[{self.id}] Parse error: {e}")
            return []

    def _search_generic(self, query: str, page: int = 1) -> List[MangaResult]:
        """Generic search for non-MangaDex modules."""
        # TODO: Implement generic search using module's methods
        source_log(f"[{self.id}] Generic search not yet implemented")
        return []

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapters using the Lua module's GetInfo function."""
        if not self._ensure_runtime():
            return []

        self._wait_for_rate_limit()

        try:
            source_log(f"[{self.id}] Getting chapters for: {manga_id}")

            # For MangaDex, use direct API
            if "mangadex" in self.module_name.lower():
                return self._get_chapters_mangadex(manga_id, language)

            # Set the URL and call GetInfo
            if manga_id.startswith("http"):
                self._runtime.set_url(manga_id)
            else:
                self._runtime.set_url(f"{self.base_url}/title/{manga_id}")

            # Call the module's GetInfo function
            get_info_func = self._module_info.get("get_info", "GetInfo")
            self._runtime.call_function(get_info_func)

            # Parse results from module
            # TODO: This needs more implementation based on FMD's output format

            return []

        except Exception as e:
            self._handle_error(str(e))
            source_log(f"[{self.id}] Chapter error: {e}")
            return []

    def _get_chapters_mangadex(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """Get chapters from MangaDex API."""
        import json

        all_chapters = []
        offset = 0
        limit = 100

        while True:
            url = f"https://api.mangadex.org/chapter?manga={manga_id}&translatedLanguage[]={language}&limit={limit}&offset={offset}&order[chapter]=asc&includes[]=scanlation_group"

            if not self._runtime.HTTP.GET(url):
                break

            doc = self._runtime.HTTP.Document.ToString()

            try:
                data = json.loads(doc)
                chapters_data = data.get("data", [])

                if not chapters_data:
                    break

                for ch in chapters_data:
                    attrs = ch.get("attributes", {})
                    chapter_num = attrs.get("chapter") or "0"

                    # Get scanlator
                    scanlator = None
                    for rel in ch.get("relationships", []):
                        if rel.get("type") == "scanlation_group":
                            scanlator = rel.get("attributes", {}).get("name")
                            break

                    all_chapters.append(ChapterResult(
                        id=ch["id"],
                        chapter=chapter_num,
                        title=attrs.get("title"),
                        volume=attrs.get("volume"),
                        language=language,
                        pages=attrs.get("pages", 0),
                        scanlator=scanlator,
                        published=attrs.get("publishAt"),
                        url=f"https://mangadex.org/chapter/{ch['id']}",
                        source=self.id
                    ))

                total = data.get("total", 0)
                if offset + limit >= total:
                    break

                offset += limit

            except Exception as e:
                source_log(f"[{self.id}] Chapter parse error: {e}")
                break

        self._handle_success()
        source_log(f"[{self.id}] Found {len(all_chapters)} chapters")
        return all_chapters

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images using the Lua module's GetPageNumber function."""
        if not self._ensure_runtime():
            return []

        self._wait_for_rate_limit()

        try:
            source_log(f"[{self.id}] Getting pages for chapter: {chapter_id}")

            # For MangaDex, use direct API
            if "mangadex" in self.module_name.lower():
                return self._get_pages_mangadex(chapter_id)

            return []

        except Exception as e:
            self._handle_error(str(e))
            source_log(f"[{self.id}] Pages error: {e}")
            return []

    def _get_pages_mangadex(self, chapter_id: str) -> List[PageResult]:
        """Get pages from MangaDex API."""
        import json

        url = f"https://api.mangadex.org/at-home/server/{chapter_id}"

        if not self._runtime.HTTP.GET(url):
            return []

        doc = self._runtime.HTTP.Document.ToString()

        try:
            data = json.loads(doc)
            base_url = data.get("baseUrl", "")
            chapter_hash = data.get("chapter", {}).get("hash", "")
            pages_data = data.get("chapter", {}).get("data", [])

            pages = []
            for idx, filename in enumerate(pages_data):
                pages.append(PageResult(
                    url=f"{base_url}/data/{chapter_hash}/{filename}",
                    index=idx,
                    headers={"User-Agent": "MangaNegus/3.0"}
                ))

            self._handle_success()
            return pages

        except Exception as e:
            source_log(f"[{self.id}] Pages parse error: {e}")
            return []

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga."""
        if "mangadex" in self.module_name.lower():
            return self._get_popular_mangadex(page)
        return []

    def _get_popular_mangadex(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga from MangaDex."""
        limit = 15
        offset = (page - 1) * limit

        url = f"https://api.mangadex.org/manga?limit={limit}&offset={offset}&includes[]=cover_art&includes[]=author&order[followedCount]=desc&availableTranslatedLanguage[]=en"

        if self._runtime.HTTP.GET(url):
            doc = self._runtime.HTTP.Document.ToString()
            return self._parse_mangadex_search(doc)

        return []


# =============================================================================
# DISCOVER LUA SOURCES
# =============================================================================

def discover_lua_sources() -> List[LuaSourceAdapter]:
    """
    Discover all available Lua modules and create adapters.

    Returns:
        List of LuaSourceAdapter instances
    """
    modules_dir = LuaSourceAdapter.LUA_MODULES_DIR
    adapters = []

    if not os.path.exists(modules_dir):
        source_log(f"Lua modules directory not found: {modules_dir}")
        return adapters

    for filename in os.listdir(modules_dir):
        if filename.endswith('.lua'):
            module_name = filename[:-4]  # Remove .lua
            try:
                adapter = LuaSourceAdapter(module_name)
                if adapter._runtime is not None:
                    adapters.append(adapter)
            except Exception as e:
                source_log(f"Failed to load Lua module {module_name}: {e}")

    return adapters


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing Lua Source Adapter...")

    # Test with MangaDex
    adapter = LuaSourceAdapter("MangaDex")

    print(f"\nModule: {adapter.name}")
    print(f"ID: {adapter.id}")
    print(f"Base URL: {adapter.base_url}")

    # Test search
    print("\nSearching for 'one piece'...")
    results = adapter.search("one piece")
    print(f"Found {len(results)} results")

    if results:
        print(f"\nFirst result: {results[0].title}")
        print(f"  ID: {results[0].id}")
        print(f"  Cover: {results[0].cover_url}")

        # Test chapters
        print(f"\nGetting chapters for {results[0].id}...")
        chapters = adapter.get_chapters(results[0].id)
        print(f"Found {len(chapters)} chapters")

        if chapters:
            print(f"\nFirst chapter: {chapters[0].chapter}")

            # Test pages
            print(f"\nGetting pages for chapter {chapters[0].id}...")
            pages = adapter.get_pages(chapters[0].id)
            print(f"Found {len(pages)} pages")

    print("\nTest complete!")

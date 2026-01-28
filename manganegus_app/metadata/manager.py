"""
================================================================================
MangaNegus v3.1 - Metadata Manager
================================================================================
Central manager for all metadata providers.

Orchestrates fetching and aggregating metadata from:
  - AniList (GraphQL)
  - MyAnimeList via Jikan (REST)
  - Kitsu (JSON:API)
  - Shikimori (REST)
  - MangaUpdates (REST)

Design follows Gemini's architecture:
  - Parallel API queries using asyncio
  - Intelligent aggregation (merge ratings, union genres)
  - Caching with TTL
  - Fuzzy title matching for ID resolution

Usage:
    manager = MetadataManager()
    await manager.initialize()

    # Search across all providers
    results = await manager.search("One Piece")

    # Get enriched metadata
    metadata = await manager.get_metadata("mangadex", "manga-id")

    await manager.close()
================================================================================
"""

import asyncio
from typing import List, Optional, Dict
import logging
from datetime import datetime, timezone
import time

from .models import UnifiedMetadata, IDMapping
from .matcher import TitleMatcher, get_cache
from .providers.base import BaseMetadataProvider

# Import all providers
from .providers.anilist import AniListProvider
from .providers.jikan import JikanProvider

logger = logging.getLogger(__name__)


# Lazy imports for Gemini's providers (they might not exist yet)
def _import_optional_provider(module_name, class_name):
    """Safely import provider, return None if not available."""
    try:
        module = __import__(f'manganegus_app.metadata.providers.{module_name}',
                           fromlist=[class_name])
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        logger.warning(f"Provider {class_name} not available: {e}")
        return None


class MetadataManager:
    """
    Central manager for metadata aggregation.

    Handles:
      - Provider initialization and lifecycle
      - Parallel queries to multiple APIs
      - Data aggregation and merging
      - Cache management
      - Error handling and fallback
    """

    def __init__(self):
        """Initialize manager with all available providers."""
        self.providers: Dict[str, BaseMetadataProvider] = {}
        self._initialized = False

    async def initialize(self):
        """
        Initialize all metadata providers.

        Call this before using the manager.
        """
        if self._initialized:
            return

        logger.info("Initializing metadata providers...")

        # Initialize core providers (always available)
        self.providers['anilist'] = AniListProvider()
        self.providers['mal'] = JikanProvider()

        # Try to initialize optional providers (from Gemini)
        KitsuProvider = _import_optional_provider('kitsu', 'KitsuProvider')
        if KitsuProvider:
            self.providers['kitsu'] = KitsuProvider()

        ShikimoriProvider = _import_optional_provider('shikimori', 'ShikimoriProvider')
        if ShikimoriProvider:
            self.providers['shikimori'] = ShikimoriProvider()

        MangaUpdatesProvider = _import_optional_provider('mangaupdates', 'MangaUpdatesProvider')
        if MangaUpdatesProvider:
            self.providers['mangaupdates'] = MangaUpdatesProvider()

        logger.info(f"✅ Initialized {len(self.providers)} metadata providers: "
                   f"{', '.join(self.providers.keys())}")

        self._initialized = True

    async def close(self):
        """Close all provider HTTP clients."""
        logger.info("Closing metadata providers...")
        for provider in self.providers.values():
            await provider.close()
        self._initialized = False

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    async def search(
        self,
        title: str,
        limit: int = 10,
        providers: Optional[List[str]] = None
    ) -> List[UnifiedMetadata]:
        """
        Search for manga across multiple providers in parallel.

        Args:
            title: Manga title to search for
            limit: Maximum results per provider
            providers: List of provider IDs to use (None = all)

        Returns:
            List of UnifiedMetadata objects (deduplicated)
        """
        if not self._initialized:
            await self.initialize()

        # Select providers
        selected_providers = {}
        if providers:
            selected_providers = {
                k: v for k, v in self.providers.items() if k in providers
            }
        else:
            selected_providers = self.providers

        if not selected_providers:
            logger.warning(f"No providers available for search")
            return []

        # Execute searches in parallel
        logger.info(f"Searching for '{title}' across {len(selected_providers)} providers...")
        tasks = [
            provider.search_series(title, limit)
            for provider in selected_providers.values()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results and handle errors
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                provider_id = list(selected_providers.keys())[i]
                logger.error(f"Search failed for {provider_id}: {result}")
                continue

            if result:
                all_results.extend(result)

        logger.info(f"Found {len(all_results)} total results")

        matcher = TitleMatcher()
        deduped: Dict[str, UnifiedMetadata] = {}
        for result in all_results:
            key = matcher.normalize_title(result.get_primary_title())
            if key not in deduped:
                deduped[key] = result
        return list(deduped.values())

    async def get_by_id(
        self,
        provider_id: str,
        manga_id: str
    ) -> Optional[UnifiedMetadata]:
        """
        Get manga metadata from specific provider.

        Args:
            provider_id: Provider ID (anilist, mal, kitsu, etc.)
            manga_id: ID in that provider's system

        Returns:
            UnifiedMetadata or None
        """
        if not self._initialized:
            await self.initialize()

        provider = self.providers.get(provider_id)
        if not provider:
            logger.error(f"Provider '{provider_id}' not found")
            return None

        return await provider.get_by_id(manga_id)

    # =========================================================================
    # AGGREGATION OPERATIONS
    # =========================================================================

    async def get_enriched_metadata(
        self,
        title: str,
        source_id: Optional[str] = None,
        source_manga_id: Optional[str] = None
    ) -> Optional[UnifiedMetadata]:
        """
        Get enriched metadata by searching all providers and merging results.

        This is the main "MetaForge" operation:
          1. Search Jikan (MAL) first (Primary - requested by user)
          2. Fallback to AniList
          3. Fetch from other providers
          4. Merge all data (ratings, genres, etc.)

        Args:
            title: Manga title
            source_id: Optional source ID (e.g., "mangadex")
            source_manga_id: Optional source-specific manga ID

        Returns:
            Aggregated UnifiedMetadata or None
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"Enriching metadata for '{title}'...")

        cache = get_cache()
        cached_mapping = cache.get(title)
        matcher = TitleMatcher()
        primary_result = None

        # --- PRIORITY 1: Jikan (MyAnimeList) ---
        mal = self.providers.get('mal')
        if mal:
            # Try ID fetch from cache first
            if cached_mapping and cached_mapping.mal_id:
                try:
                    primary_result = await mal.get_by_id(cached_mapping.mal_id)
                except Exception as e:
                    logger.warning(f"Cached MAL ID fetch failed: {e}")

            # If no ID or fetch failed, search by title
            if not primary_result:
                try:
                    mal_results = await mal.search_series(title, limit=5)
                    if mal_results:
                        primary_result = max(
                            mal_results,
                            key=lambda r: matcher.calculate_similarity(
                                title, r.get_primary_title()
                            )
                        )
                except Exception as e:
                    logger.error(f"Jikan search failed: {e}")

        # --- PRIORITY 2: AniList (Fallback) ---
        if not primary_result:
            logger.info(f"No MAL results for '{title}', falling back to AniList...")
            anilist = self.providers.get('anilist')
            if anilist:
                # Try ID fetch from cache
                if cached_mapping and cached_mapping.anilist_id:
                    try:
                        primary_result = await anilist.get_by_id(cached_mapping.anilist_id)
                    except Exception:
                        pass

                # Search by title
                if not primary_result:
                    try:
                        anilist_results = await anilist.search_series(title, limit=5)
                        if anilist_results:
                            primary_result = max(
                                anilist_results,
                                key=lambda r: matcher.calculate_similarity(
                                    title, r.get_primary_title()
                                )
                            )
                    except Exception as e:
                        logger.error(f"AniList fallback search failed: {e}")

        if not primary_result:
            logger.warning(f"No metadata found for '{title}' on any provider")
            return None

        logger.info(f"Primary match: {primary_result.get_primary_title()} "
                   f"(Source: {primary_result.primary_source})")

        # --- Step 2: Fetch from Secondary Providers ---
        secondary_results = []
        fetched_sources = {primary_result.primary_source}

        # 2a. Fetch MAL if not primary (and we have ID)
        if 'mal' not in fetched_sources:
            mal_id = primary_result.mappings.get('mal')
            if mal_id and mal:
                try:
                    res = await mal.get_by_id(mal_id)
                    if res:
                        secondary_results.append(res)
                        fetched_sources.add('mal')
                except Exception as e:
                    logger.error(f"Secondary MAL fetch failed: {e}")

        # 2b. Fetch AniList if not primary (and we have ID)
        if 'anilist' not in fetched_sources:
            anilist_id = primary_result.mappings.get('anilist')
            anilist = self.providers.get('anilist')
            if anilist_id and anilist:
                try:
                    res = await anilist.get_by_id(anilist_id)
                    if res:
                        secondary_results.append(res)
                        fetched_sources.add('anilist')
                except Exception:
                    pass

        # 2c. Search other providers by title (parallel)
        other_providers = [
            p for p_id, p in self.providers.items()
            if p_id not in fetched_sources
        ]

        if other_providers:
            tasks = [p.search_series(title, limit=3) for p in other_providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if not isinstance(result, Exception) and result:
                    # Use best match from each provider
                    best = max(
                        result,
                        key=lambda r: matcher.calculate_similarity(
                            title, r.get_primary_title()
                        )
                    )
                    secondary_results.append(best)

        # Step 3: Merge all results
        merged = self._merge_metadata(primary_result, secondary_results)

        if merged:
            mapping = IDMapping(
                source_title=title,
                anilist_id=merged.mappings.get('anilist'),
                mal_id=merged.mappings.get('mal'),
                kitsu_id=merged.mappings.get('kitsu'),
                shikimori_id=merged.mappings.get('shikimori'),
                mangaupdates_id=merged.mappings.get('mangaupdates'),
                confidence=90.0,
                matched_title=merged.get_primary_title(),
                created_at=time.time()
            )
            cache.set(title, mapping)

        logger.info(f"Enriched metadata complete: {len(secondary_results)} additional sources")

        return merged

    def _merge_metadata(
        self,
        primary: UnifiedMetadata,
        secondary: List[UnifiedMetadata]
    ) -> UnifiedMetadata:
        """
        Merge metadata from multiple providers.

        Strategy:
          - Use AniList as primary (best structure)
          - Merge ratings from all sources
          - Union genres/tags
          - Prefer highest quality cover image
          - Update mappings with all IDs

        Args:
            primary: Primary metadata (usually from AniList)
            secondary: List of secondary metadata from other providers

        Returns:
            Merged UnifiedMetadata
        """
        # Start with primary
        merged = primary

        # Merge mappings
        for meta in secondary:
            merged.mappings.update(meta.mappings)

        # Merge ratings
        for meta in secondary:
            if meta.rating_mal and not merged.rating_mal:
                merged.rating_mal = meta.rating_mal
            if meta.rating_kitsu and not merged.rating_kitsu:
                merged.rating_kitsu = meta.rating_kitsu
            if hasattr(meta, 'rating_shikimori') and not hasattr(merged, 'rating_shikimori'):
                merged.rating_shikimori = getattr(meta, 'rating_shikimori', None)

        # Calculate weighted average rating
        merged.rating = merged.merge_ratings()

        # Merge genres (union, deduplicate)
        all_genres = set(merged.genres)
        for meta in secondary:
            all_genres.update(meta.genres)
        merged.genres = sorted(list(all_genres))

        # Merge tags (union)
        all_tags = set(merged.tags)
        for meta in secondary:
            all_tags.update(meta.tags)
        merged.tags = sorted(list(all_tags))

        # Merge themes
        all_themes = set(merged.themes)
        for meta in secondary:
            all_themes.update(meta.themes)
        merged.themes = sorted(list(all_themes))

        # Use most complete data for structural fields
        for meta in secondary:
            # Prefer MangaUpdates for chapter/volume counts (most accurate)
            if meta.primary_source == 'mangaupdates':
                if meta.chapters:
                    merged.chapters = meta.chapters
                if meta.volumes:
                    merged.volumes = meta.volumes

            # Use any missing data
            if not merged.chapters and meta.chapters:
                merged.chapters = meta.chapters
            if not merged.volumes and meta.volumes:
                merged.volumes = meta.volumes

        # Merge links (union)
        existing_urls = {link.url for link in merged.links}
        for meta in secondary:
            for link in meta.links:
                if link.url not in existing_urls:
                    merged.links.append(link)
                    existing_urls.add(link.url)

        # Update popularity metrics (sum)
        for meta in secondary:
            merged.popularity += meta.popularity
            merged.favorites_count += meta.favorites_count
            if meta.members_count:
                merged.members_count = max(merged.members_count, meta.members_count)

        # Update timestamp
        merged.last_updated = time.time()

        return merged

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_available_providers(self) -> List[str]:
        """Get list of initialized provider IDs."""
        return list(self.providers.keys())

    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of all providers.

        Returns:
            Dict mapping provider ID to health status
        """
        if not self._initialized:
            await self.initialize()

        async def _check(provider_id, provider):
            try:
                await provider.search_series("test", limit=1)
                return provider_id, True
            except Exception as e:
                logger.error(f"Health check failed for {provider_id}: {e}")
                return provider_id, False

        tasks = [
            _check(provider_id, provider)
            for provider_id, provider in self.providers.items()
        ]
        results = await asyncio.gather(*tasks)
        return {provider_id: status for provider_id, status in results}


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_manager: Optional[MetadataManager] = None


async def get_metadata_manager() -> MetadataManager:
    """Get or create the global MetadataManager instance."""
    global _manager
    if _manager is None:
        _manager = MetadataManager()
        await _manager.initialize()
    return _manager

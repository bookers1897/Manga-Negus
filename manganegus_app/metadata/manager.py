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

        # TODO: Deduplicate results using fuzzy matching
        # For now, return all results
        return all_results

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
          1. Search AniList first (best for ID mapping)
          2. If confident match found, fetch from other providers using IDs
          3. Merge all data (ratings, genres, etc.)
          4. Return unified metadata

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

        # Step 1: Search AniList (best for initial match and ID mapping)
        anilist = self.providers.get('anilist')
        if not anilist:
            logger.error("AniList provider not available - cannot enrich metadata")
            return None

        anilist_results = await anilist.search_series(title, limit=5)
        if not anilist_results:
            logger.warning(f"No AniList results for '{title}'")
            return None

        # Use first result (best match)
        # TODO: Use fuzzy matching to pick best result
        primary_result = anilist_results[0]

        logger.info(f"Primary match: {primary_result.get_primary_title()} "
                   f"(AniList ID: {primary_result.mappings.get('anilist')})")

        # Step 2: Fetch from other providers using MAL ID if available
        mal_id = primary_result.mappings.get('mal')

        secondary_results = []

        if mal_id:
            # Fetch from MAL (we already have ID)
            mal = self.providers.get('mal')
            if mal:
                try:
                    mal_data = await mal.get_by_id(mal_id)
                    if mal_data:
                        secondary_results.append(mal_data)
                except Exception as e:
                    logger.error(f"MAL fetch failed: {e}")

        # Search other providers by title (in parallel)
        other_providers = [
            p for p_id, p in self.providers.items()
            if p_id not in ['anilist', 'mal']
        ]

        if other_providers:
            tasks = [p.search_series(title, limit=3) for p in other_providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if not isinstance(result, Exception) and result:
                    # Use first match from each provider
                    secondary_results.append(result[0])

        # Step 3: Merge all results
        merged = self._merge_metadata(primary_result, secondary_results)

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

        health = {}
        for provider_id, provider in self.providers.items():
            try:
                # Try a simple search
                results = await provider.search_series("test", limit=1)
                health[provider_id] = True
            except Exception as e:
                logger.error(f"Health check failed for {provider_id}: {e}")
                health[provider_id] = False

        return health


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

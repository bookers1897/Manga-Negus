"""
================================================================================
MangaNegus v3.1 - Kitsu Metadata Provider
================================================================================
Kitsu.io API client for manga metadata.

API Documentation: https://kitsu.docs.apiary.io/
Format: JSON:API (https://jsonapi.org/)

Key Features:
  - Free, no auth required
  - Rich metadata (genres, tags, ratings)
  - Good alternative titles
  - JSON:API format with relationships

Rate Limit: 60 requests/minute (conservative - no official limit published)
================================================================================
"""

from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import httpx

from .base import BaseMetadataProvider
from ..models import (
    UnifiedMetadata, MangaStatus, MangaType,
    ExternalLink, IDMapping
)

logger = logging.getLogger(__name__)


class KitsuProvider(BaseMetadataProvider):
    """
    Kitsu.io metadata provider.

    Fetches manga metadata from Kitsu's JSON:API endpoint.
    Known for good alternative titles and comprehensive tagging.
    """

    id = "kitsu"
    name = "Kitsu"
    base_url = "https://kitsu.io/api/edge"
    rate_limit = 60  # 1 req/sec conservative
    user_agent = 'MangaNegus/3.1 (https://github.com/bookers1897/Manga-Negus)'

    # Status mapping
    STATUS_MAP = {
        'current': MangaStatus.RELEASING,
        'finished': MangaStatus.FINISHED,
        'tba': MangaStatus.NOT_YET_RELEASED,
        'unreleased': MangaStatus.NOT_YET_RELEASED,
        'upcoming': MangaStatus.NOT_YET_RELEASED,
    }

    # Type mapping (subtype field)
    TYPE_MAP = {
        'manga': MangaType.MANGA,
        'novel': MangaType.NOVEL,
        'manhua': MangaType.MANHUA,
        'manhwa': MangaType.MANHWA,
        'oel': MangaType.MANGA,  # Original English Language
        'oneshot': MangaType.ONE_SHOT,
        'doujin': MangaType.DOUJINSHI,
    }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with JSON:API headers."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'application/vnd.api+json',  # JSON:API spec
                    'Content-Type': 'application/vnd.api+json'
                }
            )
        return self._client

    async def search_series(
        self,
        title: str,
        limit: int = 10
    ) -> List[UnifiedMetadata]:
        """
        Search for manga by title.

        Args:
            title: Manga title to search
            limit: Maximum results

        Returns:
            List of UnifiedMetadata objects
        """
        params = {
            'filter[text]': title,
            'filter[subtype]': 'manga,manhua,manhwa,novel,oel,oneshot,doujin',
            'page[limit]': min(limit, 20),  # Kitsu max 20
            'page[offset]': 0,
            'include': 'categories,genres',  # Include relationships
        }

        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/manga",
                params=params
            )

            if not response or 'data' not in response:
                logger.warning(f"Kitsu search returned no data for '{title}'")
                return []

            results = []
            for item in response['data']:
                try:
                    metadata = self._parse_manga(item, response.get('included', []))
                    if metadata:
                        results.append(metadata)
                except Exception as e:
                    logger.error(f"Error parsing Kitsu manga: {e}")
                    continue

            logger.info(f"Kitsu search for '{title}': {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Kitsu search failed: {e}")
            return []

    async def get_by_id(self, kitsu_id: str) -> Optional[UnifiedMetadata]:
        """
        Get manga by Kitsu ID.

        Args:
            kitsu_id: Kitsu manga ID

        Returns:
            UnifiedMetadata or None
        """
        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/manga/{kitsu_id}",
                params={'include': 'categories,genres'}
            )

            if not response or 'data' not in response:
                logger.warning(f"Kitsu manga {kitsu_id} not found")
                return None

            return self._parse_manga(response['data'], response.get('included', []))

        except Exception as e:
            logger.error(f"Kitsu get_by_id failed for {kitsu_id}: {e}")
            return None

    def _parse_manga(
        self,
        manga: Dict[str, Any],
        included: List[Dict[str, Any]] = None
    ) -> Optional[UnifiedMetadata]:
        """
        Parse Kitsu JSON:API manga object to UnifiedMetadata.

        Args:
            manga: Kitsu manga data object
            included: Related objects (categories, genres)

        Returns:
            UnifiedMetadata or None
        """
        try:
            attrs = manga.get('attributes', {})

            # Extract titles
            titles = {}
            if attrs.get('canonicalTitle'):
                titles['en'] = attrs['canonicalTitle']

            # Alternative titles
            title_variants = attrs.get('titles', {})
            for lang, title in title_variants.items():
                if title and lang not in titles:
                    titles[lang] = title

            # Abbreviated titles
            if attrs.get('abbreviatedTitles'):
                for abbrev in attrs['abbreviatedTitles']:
                    if abbrev:
                        titles['abbrev'] = abbrev
                        break

            # Status
            status_str = attrs.get('status', '').lower()
            status = self.STATUS_MAP.get(status_str, MangaStatus.UNKNOWN)

            # Type
            subtype = attrs.get('subtype', '').lower()
            manga_type = self.TYPE_MAP.get(subtype, MangaType.MANGA)

            # Rating (0-100 scale, convert to 0-10)
            rating_kitsu = None
            if attrs.get('averageRating'):
                try:
                    rating_kitsu = float(attrs['averageRating'])
                except (ValueError, TypeError):
                    pass

            # Parse categories/genres from included data
            genres = []
            tags = []
            if included:
                category_ids = set()
                # Get category relationship IDs
                if manga.get('relationships', {}).get('categories', {}).get('data'):
                    category_ids = {
                        cat['id'] for cat in manga['relationships']['categories']['data']
                    }

                # Find category names in included
                for inc in included:
                    if inc['type'] == 'categories' and inc['id'] in category_ids:
                        category_name = inc.get('attributes', {}).get('title')
                        if category_name:
                            # Kitsu doesn't distinguish genres/tags clearly
                            # Put main categories in genres, rest in tags
                            if len(genres) < 5:
                                genres.append(category_name)
                            else:
                                tags.append(category_name)

            # Start/end dates
            start_date = None
            end_date = None
            year = None

            if attrs.get('startDate'):
                try:
                    start_date = datetime.fromisoformat(attrs['startDate'].replace('Z', '+00:00'))
                    year = start_date.year
                except (ValueError, AttributeError):
                    pass

            if attrs.get('endDate'):
                try:
                    end_date = datetime.fromisoformat(attrs['endDate'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass

            # Images
            cover_image = None
            banner_image = None

            poster_image = attrs.get('posterImage', {})
            if poster_image:
                # Prefer large, fallback to medium, original
                cover_image = (
                    poster_image.get('large') or
                    poster_image.get('medium') or
                    poster_image.get('original')
                )

            cover_image_obj = attrs.get('coverImage', {})
            if cover_image_obj:
                banner_image = (
                    cover_image_obj.get('large') or
                    cover_image_obj.get('original')
                )

            # External links
            links = []
            kitsu_slug = attrs.get('slug')
            if kitsu_slug:
                links.append(ExternalLink(
                    site='Kitsu',
                    url=f"https://kitsu.io/manga/{kitsu_slug}",
                    language='en'
                ))

            # Mappings
            mappings = {
                'kitsu': manga['id']
            }

            # Check for MAL ID in relationships
            if manga.get('relationships', {}).get('mappings', {}).get('data'):
                # Would need to fetch mappings separately via included
                # For now, skip - can be added via ID resolution later
                pass

            # Create UnifiedMetadata
            return UnifiedMetadata(
                negus_id=f"kitsu:{manga['id']}",
                titles=titles,
                mappings=mappings,

                # Descriptive
                synopsis=attrs.get('synopsis') or attrs.get('description'),
                genres=genres,
                tags=tags,
                themes=[],  # Kitsu doesn't separate themes

                # Ratings
                rating=rating_kitsu / 10.0 if rating_kitsu else None,  # Convert 0-100 to 0-10
                rating_kitsu=rating_kitsu,

                # Popularity metrics
                popularity=attrs.get('popularityRank', 0),
                favorites_count=attrs.get('favoritesCount', 0),
                members_count=attrs.get('userCount', 0),

                # Structural
                status=status,
                manga_type=manga_type,
                chapters=attrs.get('chapterCount'),
                volumes=attrs.get('volumeCount'),

                # Temporal
                year=year,
                start_date=start_date,
                end_date=end_date,

                # Visual
                cover_image=cover_image,
                banner_image=banner_image,

                # Links
                links=links,

                # Source tracking
                primary_source='kitsu',
                source_priority=3,  # Lower priority than AniList/MAL
            )

        except Exception as e:
            logger.error(f"Error parsing Kitsu manga: {e}")
            return None

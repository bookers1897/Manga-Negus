"""
================================================================================
MangaNegus v3.1 - MangaUpdates Metadata Provider
================================================================================
MangaUpdates.com (Baka-Updates) API client for manga metadata.

API Documentation: https://api.mangaupdates.com/v1/docs
Format: REST JSON

Key Features:
  - Manga-specific database (most comprehensive)
  - Most accurate chapter/volume counts
  - Release tracking and scanlation info
  - Publisher and demographic data
  - No authentication required for basic queries

Rate Limit: 30 requests/minute (conservative - no official limit, but be respectful)
Special Note: MangaUpdates is best for structural data (chapters, volumes, status)
================================================================================
"""

from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from .base import BaseMetadataProvider
from ..models import (
    UnifiedMetadata, MangaStatus, MangaType,
    ExternalLink, IDMapping
)

logger = logging.getLogger(__name__)


class MangaUpdatesProvider(BaseMetadataProvider):
    """
    MangaUpdates.com metadata provider.

    Manga-specific database with the most accurate release information.
    Best for chapter counts, volume counts, and publication status.
    """

    id = "mangaupdates"
    name = "MangaUpdates"
    base_url = "https://api.mangaupdates.com/v1"
    rate_limit = 30  # 0.5 req/sec conservative

    # Status mapping
    STATUS_MAP = {
        'ongoing': MangaStatus.RELEASING,
        'complete': MangaStatus.FINISHED,
        'hiatus': MangaStatus.HIATUS,
        'cancelled': MangaStatus.CANCELLED,
        'discontinued': MangaStatus.CANCELLED,
    }

    # Type mapping
    TYPE_MAP = {
        'manga': MangaType.MANGA,
        'manhwa': MangaType.MANHWA,
        'manhua': MangaType.MANHUA,
        'novel': MangaType.NOVEL,
        'one-shot': MangaType.ONE_SHOT,
        'doujinshi': MangaType.DOUJINSHI,
        'artbook': MangaType.MANGA,
        'light novel': MangaType.NOVEL,
    }

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
        payload = {
            'search': title,
            'perpage': min(limit, 50),  # Max 50
        }

        try:
            response = await self._request(
                "POST",
                f"{self.base_url}/series/search",
                json=payload
            )

            if not response or 'results' not in response:
                logger.warning(f"MangaUpdates search returned no data for '{title}'")
                return []

            results = []
            for item in response['results']:
                try:
                    # Get full details for better data
                    series_id = item.get('record', {}).get('series_id')
                    if series_id:
                        metadata = await self.get_by_id(str(series_id))
                        if metadata:
                            results.append(metadata)
                except Exception as e:
                    logger.error(f"Error parsing MangaUpdates manga: {e}")
                    continue

            logger.info(f"MangaUpdates search for '{title}': {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"MangaUpdates search failed: {e}")
            return []

    async def get_by_id(self, mu_id: str) -> Optional[UnifiedMetadata]:
        """
        Get manga by MangaUpdates series ID.

        Args:
            mu_id: MangaUpdates series ID

        Returns:
            UnifiedMetadata or None
        """
        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/series/{mu_id}"
            )

            if not response:
                logger.warning(f"MangaUpdates manga {mu_id} not found")
                return None

            return self._parse_manga(response)

        except Exception as e:
            logger.error(f"MangaUpdates get_by_id failed for {mu_id}: {e}")
            return None

    def _parse_manga(self, manga: Dict[str, Any]) -> Optional[UnifiedMetadata]:
        """
        Parse MangaUpdates series object to UnifiedMetadata.

        Args:
            manga: MangaUpdates series data

        Returns:
            UnifiedMetadata or None
        """
        try:
            # Extract titles
            titles = {}
            if manga.get('title'):
                titles['en'] = manga['title']

            # Associated names (alternative titles)
            if manga.get('associated'):
                for assoc in manga['associated']:
                    if assoc.get('title'):
                        # MangaUpdates doesn't specify language, use 'alt'
                        titles[f"alt_{assoc.get('type', 'unknown')}"] = assoc['title']

            # Status
            status_str = manga.get('status', '').lower()
            status = self.STATUS_MAP.get(status_str, MangaStatus.UNKNOWN)

            # Type
            type_str = manga.get('type', '').lower()
            manga_type = self.TYPE_MAP.get(type_str, MangaType.MANGA)

            # Rating (MangaUpdates uses Bayesian average, 0-10 scale)
            rating_mu = None
            if manga.get('bayesian_rating'):
                try:
                    rating_mu = float(manga['bayesian_rating'])
                except (ValueError, TypeError):
                    pass

            # Genres (from categories)
            genres = []
            tags = []
            if manga.get('categories'):
                for cat in manga['categories']:
                    cat_name = cat.get('category')
                    if cat_name:
                        # MangaUpdates uses weighted categories
                        # High weight = genre, low weight = tag
                        vote_weight = cat.get('votes', 0)
                        if vote_weight > 5:  # Arbitrary threshold
                            genres.append(cat_name)
                        else:
                            tags.append(cat_name)

            # Publishers (add to tags for context)
            if manga.get('publishers'):
                for pub in manga['publishers']:
                    if pub.get('publisher_name'):
                        tags.append(f"Publisher: {pub['publisher_name']}")

            # Demographics (shounen, seinen, etc.)
            themes = []
            if manga.get('demographics'):
                for demo in manga['demographics']:
                    if demo.get('demographic'):
                        themes.append(demo['demographic'])

            # Start/end year (MangaUpdates uses year objects)
            year = None
            start_date = None
            end_date = None

            if manga.get('year'):
                year_str = manga['year']
                if isinstance(year_str, str) and year_str.isdigit():
                    year = int(year_str)
                    start_date = datetime(year, 1, 1)

            # Licensed status
            is_licensed = manga.get('licensed', False)
            if is_licensed and 'Licensed' not in tags:
                tags.append('Licensed')

            # Images
            cover_image = None
            if manga.get('image', {}).get('url', {}).get('original'):
                cover_image = manga['image']['url']['original']

            # External links
            links = []
            series_id = manga.get('series_id')
            if series_id:
                links.append(ExternalLink(
                    site='MangaUpdates',
                    url=f"https://www.mangaupdates.com/series/{series_id}",
                    language='en'
                ))

            # Official site
            if manga.get('url'):
                links.append(ExternalLink(
                    site='Official',
                    url=manga['url'],
                    language='ja'  # Usually Japanese official sites
                ))

            # Anime-Planet ID (if available in related)
            anime_planet_id = None
            if manga.get('related_series'):
                for related in manga['related_series']:
                    if 'anime-planet' in related.get('url', '').lower():
                        try:
                            anime_planet_id = related['url'].split('/')[-1]
                        except (ValueError, IndexError, AttributeError):
                            pass

            # Mappings
            mappings = {
                'mangaupdates': str(series_id) if series_id else None
            }
            if anime_planet_id:
                mappings['animeplanet'] = anime_planet_id

            # Recommendations (popularity metric - higher = more recommended)
            recommendations = manga.get('recommendations', {})
            rec_count = 0
            if isinstance(recommendations, dict):
                rec_count = recommendations.get('total', 0)

            # Create UnifiedMetadata
            return UnifiedMetadata(
                negus_id=f"mangaupdates:{series_id}",
                titles=titles,
                mappings=mappings,

                # Descriptive
                synopsis=manga.get('description'),
                genres=genres,
                tags=tags,
                themes=themes,

                # Ratings
                rating=rating_mu,
                rating_mangaupdates=rating_mu,

                # Popularity metrics
                popularity=rec_count,  # Use recommendations as popularity

                # Structural (MangaUpdates specializes in this!)
                status=status,
                manga_type=manga_type,
                chapters=manga.get('latest_chapter'),  # Most recent chapter number
                volumes=None,  # MangaUpdates doesn't track volume count well

                # Temporal
                year=year,
                start_date=start_date,

                # Visual
                cover_image=cover_image,

                # Links
                links=links,

                # Authors/Artists (store in tags for now)
                # authors=[a.get('name') for a in manga.get('authors', []) if a.get('name')],
                # artists=[a.get('name') for a in manga.get('artists', []) if a.get('name')],

                # Source tracking
                primary_source='mangaupdates',
                source_priority=2,  # High priority for chapter/volume accuracy
            )

        except Exception as e:
            logger.error(f"Error parsing MangaUpdates manga: {e}")
            return None

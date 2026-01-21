"""
================================================================================
MangaNegus v3.1 - Shikimori Metadata Provider
================================================================================
Shikimori.one API client for manga metadata.

API Documentation: https://shikimori.one/api/doc
Format: REST JSON

Key Features:
  - Russian anime/manga database (MAL clone)
  - No authentication required for read operations
  - Fast rate limits (5 req/sec = 300/min)
  - Good for additional ratings perspective
  - Rich metadata similar to MAL

Rate Limit: 300 requests/minute (5 req/sec - fastest of all providers!)
User-Agent: Required by API rules
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


class ShikimoriProvider(BaseMetadataProvider):
    """
    Shikimori.one metadata provider.

    Russian anime/manga database with fast rate limits and rich metadata.
    Similar structure to MyAnimeList.
    """

    id = "shikimori"
    name = "Shikimori"
    base_url = "https://shikimori.one/api"
    rate_limit = 300  # 5 req/sec - fastest!

    # Custom User-Agent required by Shikimori API rules
    user_agent = 'MangaNegus/3.1 (https://github.com/bookers1897/Manga-Negus)'

    # Status mapping
    STATUS_MAP = {
        'ongoing': MangaStatus.RELEASING,
        'released': MangaStatus.FINISHED,
        'anons': MangaStatus.NOT_YET_RELEASED,  # announced
        'paused': MangaStatus.HIATUS,
        'discontinued': MangaStatus.CANCELLED,
    }

    # Type mapping (kind field)
    TYPE_MAP = {
        'manga': MangaType.MANGA,
        'manhwa': MangaType.MANHWA,
        'manhua': MangaType.MANHUA,
        'novel': MangaType.NOVEL,
        'one_shot': MangaType.ONE_SHOT,
        'doujin': MangaType.DOUJINSHI,
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
        params = {
            'search': title,
            'kind': 'manga,manhwa,manhua,novel,one_shot,doujin',
            'limit': min(limit, 50),  # Shikimori max 50
            'order': 'popularity',  # Most popular first
        }

        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/mangas",
                params=params
            )

            if not response or not isinstance(response, list):
                logger.warning(f"Shikimori search returned no data for '{title}'")
                return []

            results = []
            for item in response:
                try:
                    # Get full details for each manga
                    metadata = await self._fetch_full_manga(item['id'])
                    if metadata:
                        results.append(metadata)
                except Exception as e:
                    logger.error(f"Error parsing Shikimori manga: {e}")
                    continue

            logger.info(f"Shikimori search for '{title}': {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Shikimori search failed: {e}")
            return []

    async def get_by_id(self, shikimori_id: str) -> Optional[UnifiedMetadata]:
        """
        Get manga by Shikimori ID.

        Args:
            shikimori_id: Shikimori manga ID

        Returns:
            UnifiedMetadata or None
        """
        return await self._fetch_full_manga(shikimori_id)

    async def _fetch_full_manga(self, manga_id: str) -> Optional[UnifiedMetadata]:
        """
        Fetch full manga details including genres, publishers, etc.

        Args:
            manga_id: Shikimori manga ID

        Returns:
            UnifiedMetadata or None
        """
        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/mangas/{manga_id}"
            )

            if not response:
                logger.warning(f"Shikimori manga {manga_id} not found")
                return None

            return self._parse_manga(response)

        except Exception as e:
            logger.error(f"Shikimori get_by_id failed for {manga_id}: {e}")
            return None

    def _parse_manga(self, manga: Dict[str, Any]) -> Optional[UnifiedMetadata]:
        """
        Parse Shikimori manga object to UnifiedMetadata.

        Args:
            manga: Shikimori manga data

        Returns:
            UnifiedMetadata or None
        """
        try:
            # Extract titles
            titles = {}
            if manga.get('name'):
                titles['en'] = manga['name']
            if manga.get('russian'):
                titles['ru'] = manga['russian']
            if manga.get('japanese'):
                titles['ja'] = manga['japanese']

            # Alternative titles from synonyms
            if manga.get('synonyms'):
                for idx, synonym in enumerate(manga['synonyms']):
                    if synonym:
                        titles[f'alt_{idx}'] = synonym

            # Status
            status_str = manga.get('status', '').lower()
            status = self.STATUS_MAP.get(status_str, MangaStatus.UNKNOWN)

            # Type
            kind = manga.get('kind', '').lower()
            manga_type = self.TYPE_MAP.get(kind, MangaType.MANGA)

            # Rating (Shikimori uses 0-10 scale like MAL)
            rating_shikimori = None
            if manga.get('score'):
                try:
                    rating_shikimori = float(manga['score'])
                except (ValueError, TypeError):
                    pass

            # Genres
            genres = []
            if manga.get('genres'):
                genres = [g['name'] for g in manga['genres'] if g.get('name')]

            # Publishers (store in tags since no dedicated field)
            tags = []
            if manga.get('publishers'):
                for pub in manga['publishers']:
                    if pub.get('name'):
                        tags.append(f"Publisher: {pub['name']}")

            # Start/end dates
            start_date = None
            end_date = None
            year = None

            # Shikimori uses aired_on and released_on
            if manga.get('aired_on'):
                try:
                    start_date = datetime.fromisoformat(manga['aired_on'])
                    year = start_date.year
                except (ValueError, AttributeError):
                    pass

            if manga.get('released_on'):
                try:
                    end_date = datetime.fromisoformat(manga['released_on'])
                except (ValueError, AttributeError):
                    pass

            # Images (Shikimori provides relative URLs)
            cover_image = None
            if manga.get('image', {}).get('original'):
                cover_image = f"https://shikimori.one{manga['image']['original']}"
            elif manga.get('image', {}).get('preview'):
                cover_image = f"https://shikimori.one{manga['image']['preview']}"

            # External links
            links = []
            if manga.get('url'):
                links.append(ExternalLink(
                    site='Shikimori',
                    url=f"https://shikimori.one{manga['url']}",
                    language='ru'
                ))

            # Check for MAL ID in external_links
            mal_id = None
            if manga.get('external_links'):
                for link in manga['external_links']:
                    if link.get('kind') == 'myanimelist':
                        # Extract ID from URL like myanimelist.net/manga/123
                        url = link.get('url', '')
                        if '/manga/' in url:
                            try:
                                mal_id = url.split('/manga/')[-1].split('/')[0]
                            except (ValueError, IndexError):
                                pass

            # Mappings
            mappings = {
                'shikimori': str(manga['id'])
            }
            if mal_id:
                mappings['mal'] = mal_id

            # Create UnifiedMetadata
            return UnifiedMetadata(
                negus_id=f"shikimori:{manga['id']}",
                titles=titles,
                mappings=mappings,

                # Descriptive
                synopsis=manga.get('description'),
                genres=genres,
                tags=tags,
                themes=[],

                # Ratings (store Shikimori rating separately, will be merged)
                rating=rating_shikimori,
                rating_shikimori=rating_shikimori,

                # Popularity metrics (Shikimori specific)
                popularity=manga.get('popularity', 0),
                favorites_count=manga.get('favourites', 0),

                # Structural
                status=status,
                manga_type=manga_type,
                chapters=manga.get('chapters'),
                volumes=manga.get('volumes'),

                # Temporal
                year=year,
                start_date=start_date,
                end_date=end_date,

                # Visual
                cover_image=cover_image,

                # Links
                links=links,

                # Source tracking
                primary_source='shikimori',
                source_priority=4,  # Lower priority than AniList/MAL/Kitsu
            )

        except Exception as e:
            logger.error(f"Error parsing Shikimori manga: {e}")
            return None

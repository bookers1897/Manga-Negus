"""
================================================================================
MangaNegus v3.1 - Jikan Provider (MyAnimeList)
================================================================================
REST API client for Jikan v4 (unofficial MyAnimeList API).

Jikan Features:
  - Largest user base = most reliable ratings
  - Best for rank and popularity data
  - Comprehensive manga database
  - 60 requests/min, 3 requests/sec rate limit
  - No authentication required!

API Docs: https://docs.api.jikan.moe/
GitHub: https://github.com/jikan-me/jikan

IMPORTANT: Jikan has strict rate limits and caching headers.
We must respect these to avoid being blocked.

Design follows Gemini's architecture recommendation.
================================================================================
"""

from typing import List, Optional
import logging
from datetime import datetime

from .base import BaseMetadataProvider
from ..models import UnifiedMetadata, MangaStatus, MangaType, ExternalLink

logger = logging.getLogger(__name__)


class JikanProvider(BaseMetadataProvider):
    """
    Jikan v4 API provider for MyAnimeList data.

    Jikan is a REST API that scrapes MyAnimeList. It has:
      - Aggressive caching (respect Cache-Control headers)
      - Strict rate limiting (60/min, 3/sec)
      - Rich metadata (best for popularity and rankings)
    """

    id = "mal"  # MyAnimeList
    name = "MyAnimeList (Jikan)"
    base_url = "https://api.jikan.moe/v4"
    rate_limit = 60  # 60 requests per minute (actually 3/sec)

    async def search_series(
        self,
        title: str,
        limit: int = 10
    ) -> List[UnifiedMetadata]:
        """
        Search MyAnimeList for manga via Jikan.

        Args:
            title: Manga title
            limit: Maximum results (default: 10)

        Returns:
            List of UnifiedMetadata objects
        """
        try:
            params = {
                "q": title,
                "type": "manga",
                "limit": limit,
                "order_by": "members",  # Sort by popularity
                "sort": "desc"
        }

            response = await self._request(
                "GET",
                f"{self.base_url}/manga",
                params=params
            )

            # Parse response
            if not response or 'data' not in response:
                logger.warning(f"{self.id}: No data in response")
                return []

            manga_list = response['data']
            return [self._parse_manga(manga) for manga in manga_list]

        except Exception as e:
            logger.error(f"{self.id}: Search failed for '{title}': {e}")
            return []

    async def get_by_id(
        self,
        provider_id: str
    ) -> Optional[UnifiedMetadata]:
        """
        Get manga by MyAnimeList ID.

        Args:
            provider_id: MAL ID (numeric)

        Returns:
            UnifiedMetadata or None
        """
        try:
            response = await self._request(
                "GET",
                f"{self.base_url}/manga/{provider_id}/full"  # Full endpoint for all data
            )

            if not response or 'data' not in response:
                return None

            return self._parse_manga(response['data'])

        except Exception as e:
            logger.error(f"{self.id}: Get by ID failed for '{provider_id}': {e}")
            return None

    def _parse_manga(self, manga: dict) -> UnifiedMetadata:
        """
        Parse Jikan manga object to UnifiedMetadata.

        Args:
            manga: Jikan manga dict from API response

        Returns:
            UnifiedMetadata object
        """
        import time

        # Build mappings
        mappings = {
            'mal': str(manga.get('mal_id', ''))
        }

        # Extract titles
        titles = {}
        if manga.get('title'):
            titles['romaji'] = manga['title']  # Romaji is default on MAL
        if manga.get('title_english'):
            titles['en'] = manga['title_english']
        if manga.get('title_japanese'):
            titles['ja'] = manga['title_japanese']

        # Alternative titles
        alt_titles = []
        if manga.get('title_synonyms'):
            alt_titles.extend(manga['title_synonyms'])
        if manga.get('titles'):  # v4 has detailed titles array
            for title_obj in manga['titles']:
                if title_obj.get('title') and title_obj['title'] not in titles.values():
                    alt_titles.append(title_obj['title'])

        # Status mapping
        status_map = {
            'Finished': MangaStatus.FINISHED,
            'Publishing': MangaStatus.RELEASING,
            'On Hiatus': MangaStatus.HIATUS,
            'Discontinued': MangaStatus.CANCELLED,
            'Not yet published': MangaStatus.NOT_YET_RELEASED
        }
        status = status_map.get(manga.get('status'), None)

        # Type mapping
        type_map = {
            'Manga': MangaType.MANGA,
            'Novel': MangaType.NOVEL,
            'One-shot': MangaType.ONE_SHOT,
            'Doujinshi': MangaType.DOUJINSHI,
            'Manhwa': MangaType.MANHWA,
            'Manhua': MangaType.MANHUA
        }
        manga_type = type_map.get(manga.get('type'), None)

        # Genres (extract names from genre objects)
        genres = [
            genre['name']
            for genre in manga.get('genres', [])
        ]

        # Themes (MAL has explicit themes category)
        themes = [
            theme['name']
            for theme in manga.get('themes', [])
        ]

        # Demographics (Shounen, Seinen, etc.)
        demographics = [
            demo['name']
            for demo in manga.get('demographics', [])
        ]

        # Extract authors
        author = None
        artist = None
        authors_list = []

        for author_obj in manga.get('authors', []):
            name = author_obj.get('name', '')
            if not name:
                continue

            role = author_obj.get('type', '')
            authors_list.append({'name': name, 'role': role})

            # Guess primary author/artist from role
            if not author and ('story' in role.lower() or role == 'Author'):
                author = name
            elif not artist and 'art' in role.lower():
                artist = name

        # If no artist specified, use first author
        if not artist and authors_list:
            artist = authors_list[0]['name']

        # Rating (MAL uses 0-10 scale)
        rating_mal = manga.get('score')  # 0-10

        # Popularity metrics
        popularity_rank = manga.get('popularity')
        rank = manga.get('rank')  # Overall ranking
        members_count = manga.get('members', 0)
        favorites_count = manga.get('favorites', 0)

        # Cover image
        images = manga.get('images', {}).get('jpg', {})
        cover_image = images.get('large_image_url') or images.get('image_url')
        cover_image_medium = images.get('image_url')

        # WebP alternative (higher quality)
        webp_images = manga.get('images', {}).get('webp', {})
        if webp_images.get('large_image_url'):
            cover_image = webp_images['large_image_url']

        # Dates
        start_date = None
        if manga.get('published') and manga['published'].get('from'):
            try:
                start_date = datetime.fromisoformat(
                    manga['published']['from'].replace('Z', '+00:00')
                )
            except:
                pass

        end_date = None
        if manga.get('published') and manga['published'].get('to'):
            try:
                end_date = datetime.fromisoformat(
                    manga['published']['to'].replace('Z', '+00:00')
                )
            except:
                pass

        # Year (from aired object)
        year = None
        if manga.get('published', {}).get('prop', {}).get('from', {}).get('year'):
            year = manga['published']['prop']['from']['year']
        elif start_date:
            year = start_date.year

        # Serialization (magazine)
        serialization = None
        if manga.get('serializations') and manga['serializations']:
            serialization = manga['serializations'][0].get('name')

        # External links
        links = []
        if manga.get('url'):  # MAL URL
            links.append(ExternalLink(site='MyAnimeList', url=manga['url']))

        # Build UnifiedMetadata
        return UnifiedMetadata(
            negus_id=f"mal:{manga['mal_id']}",
            mappings=mappings,
            titles=titles,
            alt_titles=alt_titles,
            synopsis=manga.get('synopsis', ''),
            description=manga.get('background', ''),  # MAL has background info
            status=status,
            manga_type=manga_type,
            genres=genres,
            themes=themes,
            demographics=demographics,
            author=author,
            artist=artist,
            authors=authors_list,
            rating_mal=rating_mal,
            popularity_rank=popularity_rank,
            rank=rank,
            members_count=members_count,
            favorites_count=favorites_count,
            volumes=manga.get('volumes'),
            chapters=manga.get('chapters'),
            cover_image=cover_image,
            cover_image_medium=cover_image_medium,
            year=year,
            start_date=start_date,
            end_date=end_date,
            serialization=serialization,
            links=links,
            last_updated=time.time(),
            primary_source='mal'
        )

"""
================================================================================
MangaNegus v3.1 - AniList Provider
================================================================================
GraphQL client for AniList API.

AniList Features:
  - Best source for cross-API ID mapping
  - Rich metadata (genres, tags, ratings)
  - GraphQL = fetch exactly what we need (efficient)
  - 90 requests/min rate limit
  - No authentication required!

API Docs: https://anilist.gitbook.io/anilist-apiv2-docs/
GraphiQL: https://anilist.co/graphiql

Design follows Gemini's architecture recommendation.
================================================================================
"""

from typing import List, Optional
import logging
from datetime import datetime

from .base import BaseMetadataProvider
from ..models import UnifiedMetadata, MangaStatus, MangaType, ExternalLink

logger = logging.getLogger(__name__)


class AniListProvider(BaseMetadataProvider):
    """
    AniList GraphQL API provider.

    GraphQL allows us to request exactly the fields we need,
    reducing bandwidth and speeding up responses.
    """

    id = "anilist"
    name = "AniList"
    base_url = "https://graphql.anilist.co"
    rate_limit = 90  # 90 requests per minute

    # GraphQL query for searching manga
    SEARCH_QUERY = """
    query ($search: String, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(search: $search, type: MANGA, sort: SEARCH_MATCH) {
          id
          idMal
          title {
            romaji
            english
            native
          }
          synonyms
          description
          status
          format
          genres
          tags {
            name
            rank
          }
          averageScore
          popularity
          favourites
          chapters
          volumes
          coverImage {
            extraLarge
            large
            medium
          }
          bannerImage
          startDate {
            year
            month
            day
          }
          endDate {
            year
            month
            day
          }
          staff {
            edges {
              role
              node {
                name {
                  full
                }
              }
            }
          }
          externalLinks {
            site
            url
          }
          isAdult
        }
      }
    }
    """

    # GraphQL query for getting by ID
    GET_BY_ID_QUERY = """
    query ($id: Int) {
      Media(id: $id, type: MANGA) {
        id
        idMal
        title {
          romaji
          english
          native
        }
        synonyms
        description
        status
        format
        genres
        tags {
          name
          rank
        }
        averageScore
        popularity
        favourites
        chapters
        volumes
        coverImage {
          extraLarge
          large
          medium
        }
        bannerImage
        startDate {
          year
          month
          day
        }
        endDate {
          year
          month
          day
        }
        staff {
          edges {
            role
            node {
              name {
                full
              }
            }
          }
        }
        externalLinks {
          site
          url
        }
        isAdult
      }
    }
    """

    async def search_series(
        self,
        title: str,
        limit: int = 10
    ) -> List[UnifiedMetadata]:
        """
        Search AniList for manga by title.

        Args:
            title: Manga title
            limit: Maximum results (default: 10)

        Returns:
            List of UnifiedMetadata objects
        """
        try:
            variables = {
                "search": title,
                "page": 1,
                "perPage": limit
            }

            response = await self._request(
                "POST",
                self.base_url,
                json={
                    "query": self.SEARCH_QUERY,
                    "variables": variables
                }
            )

            # Parse response
            if not response or 'data' not in response:
                logger.warning(f"{self.id}: No data in response")
                return []

            media_list = response['data']['Page']['media']
            return [self._parse_media(media) for media in media_list]

        except Exception as e:
            logger.error(f"{self.id}: Search failed for '{title}': {e}")
            return []

    async def get_by_id(
        self,
        provider_id: str
    ) -> Optional[UnifiedMetadata]:
        """
        Get manga by AniList ID.

        Args:
            provider_id: AniList ID (numeric)

        Returns:
            UnifiedMetadata or None
        """
        try:
            variables = {"id": int(provider_id)}

            response = await self._request(
                "POST",
                self.base_url,
                json={
                    "query": self.GET_BY_ID_QUERY,
                    "variables": variables
                }
            )

            if not response or 'data' not in response or not response['data']['Media']:
                return None

            return self._parse_media(response['data']['Media'])

        except Exception as e:
            logger.error(f"{self.id}: Get by ID failed for '{provider_id}': {e}")
            return None

    def _parse_media(self, media: dict) -> UnifiedMetadata:
        """
        Parse AniList media object to UnifiedMetadata.

        Args:
            media: AniList media dict from GraphQL response

        Returns:
            UnifiedMetadata object
        """
        import time

        # Build mappings
        mappings = {
            'anilist': str(media.get('id', ''))
        }
        if media.get('idMal'):
            mappings['mal'] = str(media['idMal'])

        # Extract titles
        titles = {}
        title_obj = media.get('title', {})
        if title_obj.get('english'):
            titles['en'] = title_obj['english']
        if title_obj.get('romaji'):
            titles['romaji'] = title_obj['romaji']
        if title_obj.get('native'):
            titles['ja'] = title_obj['native']

        # Alternative titles
        alt_titles = media.get('synonyms', [])

        # Status mapping
        status_map = {
            'FINISHED': MangaStatus.FINISHED,
            'RELEASING': MangaStatus.RELEASING,
            'NOT_YET_RELEASED': MangaStatus.NOT_YET_RELEASED,
            'CANCELLED': MangaStatus.CANCELLED,
            'HIATUS': MangaStatus.HIATUS
        }
        status = status_map.get(media.get('status'), None)

        # Format/Type mapping
        format_map = {
            'MANGA': MangaType.MANGA,
            'NOVEL': MangaType.NOVEL,
            'ONE_SHOT': MangaType.ONE_SHOT,
            'MANHWA': MangaType.MANHWA,
            'MANHUA': MangaType.MANHUA
        }
        manga_type = format_map.get(media.get('format'), None)

        # Genres
        genres = media.get('genres', [])

        # Tags (filter by rank > 60 for relevance)
        tags = [
            tag['name']
            for tag in media.get('tags', [])
            if tag.get('rank', 0) > 60
        ]

        # Extract staff (author/artist)
        author = None
        artist = None
        authors_list = []

        for edge in media.get('staff', {}).get('edges', []):
            role = edge.get('role', '').lower()
            name = edge.get('node', {}).get('name', {}).get('full', '')

            if not name:
                continue

            authors_list.append({'name': name, 'role': edge.get('role', '')})

            if 'story' in role or 'original creator' in role:
                author = name
            elif 'art' in role:
                artist = name

        # Rating (AniList uses 0-100 scale)
        rating_anilist = media.get('averageScore')  # 0-100

        # Cover images
        cover_obj = media.get('coverImage', {})
        cover_image = cover_obj.get('extraLarge') or cover_obj.get('large')
        cover_image_large = cover_obj.get('large')
        cover_image_medium = cover_obj.get('medium')

        # Banner
        banner_image = media.get('bannerImage')

        # Dates
        start_date = None
        if media.get('startDate'):
            sd = media['startDate']
            if sd.get('year'):
                try:
                    start_date = datetime(
                        sd['year'],
                        sd.get('month', 1),
                        sd.get('day', 1)
                    )
                except:
                    pass

        end_date = None
        if media.get('endDate'):
            ed = media['endDate']
            if ed.get('year'):
                try:
                    end_date = datetime(
                        ed['year'],
                        ed.get('month', 1),
                        ed.get('day', 1)
                    )
                except:
                    pass

        # Year
        year = media.get('startDate', {}).get('year')

        # External links
        links = [
            ExternalLink(site=link['site'], url=link['url'])
            for link in media.get('externalLinks', [])
        ]

        # Build UnifiedMetadata
        return UnifiedMetadata(
            negus_id=f"anilist:{media['id']}",
            mappings=mappings,
            titles=titles,
            alt_titles=alt_titles,
            synopsis=media.get('description', '').replace('<br>', '\n') if media.get('description') else '',
            status=status,
            manga_type=manga_type,
            genres=genres,
            tags=tags,
            author=author,
            artist=artist,
            authors=authors_list,
            rating_anilist=rating_anilist,
            popularity=media.get('popularity', 0),
            favorites_count=media.get('favourites', 0),
            volumes=media.get('volumes'),
            chapters=media.get('chapters'),
            cover_image=cover_image,
            cover_image_large=cover_image_large,
            cover_image_medium=cover_image_medium,
            banner_image=banner_image,
            year=year,
            start_date=start_date,
            end_date=end_date,
            links=links,
            is_adult=media.get('isAdult', False),
            last_updated=time.time(),
            primary_source='anilist'
        )

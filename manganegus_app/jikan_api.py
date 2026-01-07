"""
Jikan API Client - MyAnimeList metadata provider
Official documentation: https://docs.api.jikan.moe/
"""

import requests
from typing import Optional, Dict, List
import time


class JikanAPI:
    """Client for Jikan v4 API (MyAnimeList)"""

    BASE_URL = "https://api.jikan.moe/v4"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MangaNegus/3.0'
        })
        self._last_request_time = 0
        self._rate_limit_delay = 0.34  # Jikan has 3 req/sec limit, so ~333ms between requests

    def _rate_limit(self):
        """Ensure we don't exceed Jikan's rate limit (3 req/sec)"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def search_manga(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for manga by title.

        Args:
            query: Manga title to search for
            limit: Maximum number of results (default 10, max 25)

        Returns:
            List of manga objects with metadata
        """
        self._rate_limit()

        try:
            params = {
                'q': query,
                'limit': min(limit, 25),
                'order_by': 'popularity',  # Sort by popularity for best matches
                'type': 'manga'
            }

            resp = self.session.get(
                f"{self.BASE_URL}/manga",
                params=params,
                timeout=10
            )

            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []

            for item in data.get('data', []):
                results.append(self._parse_manga(item))

            return results

        except Exception as e:
            print(f"Jikan search error: {e}")
            return []

    def get_top_manga(self, limit: int = 20, page: int = 1) -> List[Dict]:
        """
        Get top/popular manga from MyAnimeList.

        Args:
            limit: Maximum number of results (default 20, max 25)
            page: Page number for pagination

        Returns:
            List of top manga with metadata
        """
        self._rate_limit()

        try:
            params = {
                'limit': min(limit, 25),
                'page': page,
                'type': 'manga'
            }

            resp = self.session.get(
                f"{self.BASE_URL}/top/manga",
                params=params,
                timeout=10
            )

            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []

            for item in data.get('data', []):
                results.append(self._parse_manga(item))

            return results

        except Exception as e:
            print(f"Jikan top manga error: {e}")
            return []

    def get_seasonal_manga(self, limit: int = 20) -> List[Dict]:
        """
        Get currently airing/publishing seasonal manga.

        Returns:
            List of seasonal manga with metadata
        """
        self._rate_limit()

        try:
            # Get current season
            resp = self.session.get(
                f"{self.BASE_URL}/seasons/now",
                timeout=10
            )

            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []

            # Filter for manga only
            for item in data.get('data', [])[:limit]:
                if item.get('type') in ['Manga', 'Manhwa', 'Manhua', 'Novel', 'One-shot']:
                    results.append(self._parse_manga(item))

            return results

        except Exception as e:
            print(f"Jikan seasonal error: {e}")
            return []

    def get_manga_by_id(self, mal_id: int) -> Optional[Dict]:
        """
        Get detailed manga information by MyAnimeList ID.

        Args:
            mal_id: MyAnimeList manga ID

        Returns:
            Manga metadata dict or None
        """
        self._rate_limit()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/manga/{mal_id}",
                timeout=10
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            return self._parse_manga(data.get('data', {}))

        except Exception as e:
            print(f"Jikan get_manga error: {e}")
            return None

    def _parse_manga(self, item: Dict) -> Dict:
        """Parse Jikan manga object into our standard format"""

        # Get the best quality image
        images = item.get('images', {})
        cover_url = (
            images.get('webp', {}).get('large_image_url') or
            images.get('jpg', {}).get('large_image_url') or
            images.get('webp', {}).get('image_url') or
            images.get('jpg', {}).get('image_url')
        )

        # Extract genres
        genres = [g['name'] for g in item.get('genres', [])]
        themes = [t['name'] for t in item.get('themes', [])]
        demographics = [d['name'] for d in item.get('demographics', [])]

        # Combine all tags
        all_tags = genres + themes + demographics

        # Get authors
        authors = item.get('authors', [])
        author = authors[0]['name'] if authors else None

        # Parse status
        status_map = {
            'Finished': 'Completed',
            'Publishing': 'Ongoing',
            'On Hiatus': 'Hiatus',
            'Discontinued': 'Cancelled'
        }
        status = status_map.get(item.get('status', ''), item.get('status', ''))

        return {
            'mal_id': item.get('mal_id'),
            'title': item.get('title'),
            'title_english': item.get('title_english'),
            'title_japanese': item.get('title_japanese'),
            'cover_url': cover_url,
            'synopsis': item.get('synopsis', ''),
            'background': item.get('background', ''),
            'type': item.get('type', 'Manga'),  # Manga, Novel, One-shot, etc.
            'status': status,
            'year': item.get('published', {}).get('prop', {}).get('from', {}).get('year'),
            'chapters': item.get('chapters'),
            'volumes': item.get('volumes'),
            'rating': {
                'average': item.get('score'),
                'count': item.get('scored_by')
            },
            'genres': genres,
            'tags': all_tags,
            'author': author,
            'url': item.get('url'),
            'popularity': item.get('popularity'),
            'rank': item.get('rank')
        }

    def enrich_search_results(self, manga_list: List[Dict]) -> List[Dict]:
        """
        Enrich manga search results with Jikan metadata.

        Args:
            manga_list: List of manga dicts from sources with 'title' field

        Returns:
            Same list but with Jikan metadata merged in
        """
        enriched = []

        for manga in manga_list:
            # Search Jikan for this manga
            jikan_results = self.search_manga(manga['title'], limit=1)

            if jikan_results:
                # Merge Jikan metadata with source data
                jikan_data = jikan_results[0]

                # Keep original source data but add Jikan metadata
                enriched_manga = {
                    **manga,  # Original source data (id, source, title, etc.)
                    'cover_url': jikan_data['cover_url'],  # Replace cover with high-quality Jikan image
                    'synopsis': jikan_data.get('synopsis'),
                    'rating': jikan_data.get('rating'),
                    'genres': jikan_data.get('genres', []),
                    'tags': jikan_data.get('tags', []),
                    'author': jikan_data.get('author'),
                    'status': jikan_data.get('status'),
                    'type': jikan_data.get('type'),
                    'year': jikan_data.get('year'),
                    'volumes': jikan_data.get('volumes'),
                    'mal_id': jikan_data.get('mal_id'),
                }
                enriched.append(enriched_manga)
            else:
                # No Jikan match, keep original
                enriched.append(manga)

        return enriched


# Singleton instance
_jikan_client = None

def get_jikan_client() -> JikanAPI:
    """Get singleton Jikan API client"""
    global _jikan_client
    if _jikan_client is None:
        _jikan_client = JikanAPI()
    return _jikan_client

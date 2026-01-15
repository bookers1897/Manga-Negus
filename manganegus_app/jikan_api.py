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
        self._genre_cache = {'timestamp': 0, 'map': {}}

    def _rate_limit(self):
        """Ensure we don't exceed Jikan's rate limit (3 req/sec)"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def search_manga(self, query: str, limit: int = 10, filters: Optional[Dict] = None, sfw: bool = True) -> List[Dict]:
        """
        Search for manga by title.

        Args:
            query: Manga title to search for
            limit: Maximum number of results (default 10, max 25)
            filters: Additional filter parameters
            sfw: Filter out adult content (default True)

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

            # SFW filter - enabled by default
            if sfw:
                params['sfw'] = 'true'

            if filters:
                # Only include supported filter params
                for key in ('status', 'type', 'order_by', 'sort', 'min_score', 'max_score', 'start_date', 'end_date', 'genres', 'genres_exclude'):
                    if filters.get(key) not in (None, ''):
                        params[key] = filters.get(key)
                # Handle SFW filter specially - needs to be string 'true'/'false'
                if 'sfw' in filters:
                    sfw_val = filters.get('sfw')
                    if sfw_val is True or sfw_val == 'true' or sfw_val == '1':
                        params['sfw'] = 'true'
                    elif sfw_val is False or sfw_val == 'false' or sfw_val == '0':
                        params['sfw'] = 'false'

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

    def get_top_manga(self, limit: int = 20, page: int = 1, sfw: bool = True) -> List[Dict]:
        """
        Get top/popular manga from MyAnimeList.

        Args:
            limit: Maximum number of results (default 20, max 25)
            page: Page number for pagination
            sfw: Filter out adult content (default True)

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

            # SFW filter - enabled by default
            if sfw:
                params['sfw'] = 'true'

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

    def get_seasonal_manga(self, limit: int = 20, page: int = 1) -> List[Dict]:
        """
        Get currently airing/publishing seasonal manga.

        Returns:
            List of seasonal manga with metadata
        """
        self._rate_limit()

        try:
            params = {'page': page}

            # Get current season
            resp = self.session.get(
                f"{self.BASE_URL}/seasons/now",
                params=params,
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

    def get_recommendations(self, mal_id: int, limit: int = 8) -> List[Dict]:
        """
        Get manga recommendations based on a specific manga.
        Uses MyAnimeList's user-generated recommendations.

        Args:
            mal_id: MyAnimeList manga ID to get recommendations for
            limit: Maximum number of recommendations (default 8)

        Returns:
            List of recommended manga with metadata
        """
        self._rate_limit()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/manga/{mal_id}/recommendations",
                timeout=10
            )

            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []

            for item in data.get('data', [])[:limit]:
                entry = item.get('entry', {})
                if entry:
                    results.append(self._parse_manga(entry))

            return results

        except Exception as e:
            print(f"Jikan recommendations error: {e}")
            return []

    def _fetch_genre_map(self) -> Dict[str, int]:
        """Fetch and cache genre name -> id map."""
        cache_ttl = 7 * 24 * 60 * 60
        now = time.time()
        if self._genre_cache['map'] and (now - self._genre_cache['timestamp']) < cache_ttl:
            return self._genre_cache['map']

        try:
            self._rate_limit()
            resp = self.session.get(f"{self.BASE_URL}/genres/manga", timeout=10)
            if resp.status_code != 200:
                return self._genre_cache['map']
            data = resp.json().get('data', [])
            mapping = {}
            for item in data:
                name = item.get('name')
                if name:
                    mapping[name.lower()] = item.get('mal_id')
            self._genre_cache = {'timestamp': now, 'map': mapping}
            return mapping
        except Exception:
            return self._genre_cache['map']

    def resolve_genre_ids(self, names: List[str]) -> List[int]:
        """Resolve genre names or ids to MAL genre ids."""
        if not names:
            return []
        mapping = self._fetch_genre_map()
        ids = []
        for name in names:
            if name is None:
                continue
            try:
                as_int = int(name)
                ids.append(as_int)
                continue
            except (ValueError, TypeError):
                pass
            lookup = mapping.get(str(name).strip().lower())
            if lookup:
                ids.append(int(lookup))
        # Deduplicate
        return sorted(set(ids))

    def _parse_manga(self, item: Dict) -> Dict:
        """Parse Jikan manga object into our standard format"""

        # Get the best quality image
        images = item.get('images', {})
        cover_url_large = (
            images.get('webp', {}).get('large_image_url') or
            images.get('jpg', {}).get('large_image_url')
        )
        cover_url_medium = (
            images.get('webp', {}).get('image_url') or
            images.get('jpg', {}).get('image_url')
        )
        cover_url_small = (
            images.get('webp', {}).get('small_image_url') or
            images.get('jpg', {}).get('small_image_url')
        )
        cover_url = cover_url_large or cover_url_medium or cover_url_small

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
            'cover_url_large': cover_url_large,
            'cover_url_medium': cover_url_medium,
            'cover_url_small': cover_url_small,
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

    def get_hidden_gems(self, limit: int = 20, page: int = 1, sfw: bool = True) -> List[Dict]:
        """
        Get "hidden gems" - lesser-known but high-quality manga.

        Criteria:
        - Score between 7.0 and 8.5 (good but not mega-popular)
        - Popularity rank > 500 (not mainstream)
        - Randomized results for variety

        Args:
            limit: Maximum number of results
            page: Page number for variety
            sfw: Filter out adult content (default True)

        Returns:
            List of manga that are quality but lesser-known
        """
        self._rate_limit()

        try:
            import random

            # Use search with filters for lesser-known manga
            # Jikan's search can filter by score, but not popularity rank
            # So we'll get a larger set and filter client-side
            params = {
                'limit': 25,  # Get max to filter from
                'page': page,
                'type': 'manga',
                'min_score': 7.0,
                'max_score': 8.5,
                'order_by': 'score',
                'sort': 'desc'
            }

            # SFW filter - enabled by default
            if sfw:
                params['sfw'] = 'true'

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
                # Filter for lesser-known (popularity > 500)
                if item.get('popularity', 0) > 500:
                    results.append(self._parse_manga(item))

            # Randomize for variety (different results each time)
            random.shuffle(results)

            return results[:limit]

        except Exception as e:
            print(f"Jikan hidden gems error: {e}")
            return []

    def get_blended_popular(self, limit: int = 20, page: int = 1, sfw: bool = True) -> List[Dict]:
        """
        Get a blend of trending (seasonal) and all-time popular manga.

        Mix ratio: 60% top popular, 40% trending seasonal

        Args:
            limit: Total number of results
            page: Page number
            sfw: Filter out adult content (default True)

        Returns:
            Blended list of popular manga
        """
        try:
            # Calculate split (60% popular, 40% trending)
            popular_count = int(limit * 0.6)
            trending_count = limit - popular_count

            # Get both feeds (pass through SFW filter)
            popular = self.get_top_manga(limit=popular_count, page=page, sfw=sfw)
            trending = self.get_seasonal_manga(limit=trending_count, page=page)

            # Merge and interleave for variety
            result = []
            max_len = max(len(popular), len(trending))

            for i in range(max_len):
                # Add from popular first (60% weight)
                if i < len(popular):
                    result.append(popular[i])
                # Then add from trending (40% weight)
                if i < len(trending):
                    result.append(trending[i])

            return result[:limit]

        except Exception as e:
            print(f"Jikan blended popular error: {e}")
            # Fallback to just top manga
            return self.get_top_manga(limit=limit, page=page)


# Singleton instance
_jikan_client = None

def get_jikan_client() -> JikanAPI:
    """Get singleton Jikan API client"""
    global _jikan_client
    if _jikan_client is None:
        _jikan_client = JikanAPI()
    return _jikan_client

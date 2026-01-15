from flask import Blueprint, jsonify, request
import asyncio
from sources import get_source_manager
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.rate_limit import limit_heavy, limit_medium, limit_light
from manganegus_app.search.smart_search import SmartSearch
from manganegus_app.jikan_api import get_jikan_client
from .validators import validate_fields, validate_pagination, validate_source_id, sanitize_string

manga_bp = Blueprint('manga_api', __name__, url_prefix='/api')

# Initialize smart search
_smart_search = SmartSearch()

def _enrich_with_jikan(manga_list):
    """Enrich manga list with Jikan metadata (MAL data)"""
    try:
        jikan = get_jikan_client()
        enriched = []

        for manga in manga_list:
            # Search Jikan for this manga
            jikan_results = jikan.search_manga(manga.get('title', ''), limit=1)

            if jikan_results:
                jikan_data = jikan_results[0]
                # Merge Jikan metadata
                manga_dict = manga if isinstance(manga, dict) else manga.to_dict()
                manga_dict.update({
                    'cover_url': jikan_data['cover_url'],
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
                })
                enriched.append(manga_dict)
            else:
                enriched.append(manga if isinstance(manga, dict) else manga.to_dict())

        return enriched
    except Exception as e:
        log(f"⚠️ Jikan enrichment failed: {e}")
        # Return original data if enrichment fails
        return [m if isinstance(m, dict) else m.to_dict() for m in manga_list]

def _run_async(coro):
    """Run async coroutine safely from sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    return loop.run_until_complete(coro)

@manga_bp.route('/search', methods=['POST'])
@csrf_protect
@limit_heavy
def search():
    """Search for manga using Jikan (MyAnimeList) API."""
    data = request.get_json(silent=True) or {}
    query = sanitize_string(data.get('query', ''), max_length=200).strip()
    filters = data.get('filters') or {}

    # Validate pagination
    _, limit, _ = validate_pagination(None, data.get('limit', 15))
    limit = min(limit, 25)  # Cap search limit

    if not query:
        return jsonify([])

    if len(query) < 2:
        return jsonify({'error': 'Query too short (min 2 characters)'}), 400

    source_id = ''
    if isinstance(filters, dict):
        source_id = (filters.get('source') or '').strip()
    if source_id:
        log(f"🔍 Searching source {source_id} for '{query}'...")
        manager = get_source_manager()
        results = manager.search(query, source_id=source_id)
        payload = []
        for result in results[:limit]:
            data = result.to_dict() if hasattr(result, 'to_dict') else dict(result)
            cover = data.get('cover') or data.get('cover_url')
            data['cover'] = cover
            data['cover_url'] = cover
            data['source'] = data.get('source') or source_id
            payload.append(data)
        return jsonify(payload)

    log(f"🔍 Searching Jikan for '{query}'...")
    jikan = get_jikan_client()
    jikan_filters = {}

    # SFW filter - enabled by default unless explicitly disabled
    # Set sfw=false in filters to include adult content
    sfw_mode = True  # Default to safe-for-work
    if isinstance(filters, dict):
        sfw_setting = filters.get('sfw')
        if sfw_setting is False or sfw_setting == 'false' or sfw_setting == '0':
            sfw_mode = False
    if sfw_mode:
        jikan_filters['sfw'] = True  # Filter out adult content

    if isinstance(filters, dict):
        status = filters.get('status') or ''
        manga_type = filters.get('type') or ''
        sort = filters.get('sort') or ''
        order = filters.get('order') or ''
        min_score = filters.get('scoreMin')
        max_score = filters.get('scoreMax')
        year_start = filters.get('yearStart')
        year_end = filters.get('yearEnd')

        if status:
            jikan_filters['status'] = status
        if manga_type:
            jikan_filters['type'] = manga_type
        if sort:
            jikan_filters['order_by'] = sort
        if order:
            jikan_filters['sort'] = order
        if min_score not in (None, ''):
            jikan_filters['min_score'] = min_score
        if max_score not in (None, ''):
            jikan_filters['max_score'] = max_score
        if year_start:
            jikan_filters['start_date'] = f"{year_start}-01-01"
        if year_end:
            jikan_filters['end_date'] = f"{year_end}-12-31"

        def normalize_list(value):
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
            if isinstance(value, str):
                return [v.strip() for v in value.split(',') if v.strip()]
            return []

        include_names = normalize_list(filters.get('genres')) + normalize_list(filters.get('demographics'))
        exclude_names = normalize_list(filters.get('exclude'))
        genre_ids = filters.get('genre_ids') or filters.get('genreIds')
        if isinstance(genre_ids, list):
            include_ids = [str(g).strip() for g in genre_ids if str(g).strip()]
        else:
            include_ids = []

        include_ids = include_ids or [str(g) for g in jikan.resolve_genre_ids(include_names)]
        exclude_ids = [str(g) for g in jikan.resolve_genre_ids(exclude_names)]

        if include_ids:
            jikan_filters['genres'] = ','.join(include_ids)
        if exclude_ids:
            jikan_filters['genres_exclude'] = ','.join(exclude_ids)

    log(f"🔍 Jikan filters: {jikan_filters}")
    results = jikan.search_manga(query, limit=limit, filters=jikan_filters)
    log(f"✅ Jikan returned {len(results)} results")

    return jsonify(results)

@manga_bp.route('/search/smart', methods=['POST'])
@csrf_protect
@limit_heavy
def smart_search():
    """
    Smart search with parallel queries, deduplication, and metadata enrichment.

    Request:
        {
            "query": "Naruto",
            "limit": 10,  // Optional, default 10
            "sources": ["mangadex", "manganato"],  // Optional, default top 5
            "enrich_metadata": true  // Optional, default true
        }

    Returns:
        [
            {
                "title": "Naruto",
                "primary_source": "WeebCentral",
                "primary_source_id": "lua-weebcentral",
                "sources": [
                    {
                        "source_id": "lua-weebcentral",
                        "source_name": "WeebCentral",
                        "manga_id": "...",
                        "url": "...",
                        "chapters": 700,
                        "priority": 1
                    },
                    ...
                ],
                "total_chapters": 1170,
                "cover_url": "https://...",
                "description": "...",
                "alt_titles": ["NARUTO", "ナルト"],
                "metadata": {
                    "rating": 8.2,
                    "genres": ["Action", "Adventure"],
                    "tags": ["Ninjas", "Friendship"],
                    "status": "finished",
                    "year": 1999,
                    "synopsis": "..."
                },
                "match_confidence": 95.0
            },
            ...
        ]
    """
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    limit = data.get('limit', 10)
    sources = data.get('sources')  # None = use default top 5
    enrich_metadata = data.get('enrich_metadata', True)

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    try:
        # Run async smart search
        results = _run_async(
            _smart_search.search(
                query,
                limit=limit,
                sources=sources,
                enrich_metadata=enrich_metadata
            )
        )

        return jsonify({
            'results': results,
            'count': len(results),
            'query': query
        })

    except Exception as e:
        log(f"❌ Smart search failed: {e}")
        return jsonify({'error': str(e)}), 500

@manga_bp.route('/detect_url', methods=['POST'])
@csrf_protect
@limit_medium
def detect_url():
    """Detect source and manga ID from a URL."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    result = manager.detect_source_from_url(url)
    if not result:
        return jsonify({'error': 'Could not detect source from URL.'}), 404
    try:
        manga = manager.get_manga_details(result['manga_id'], result['source_id'])
        if manga:
            result['title'] = manga.title
            result['cover'] = manga.cover_url
    except Exception as e:
        log(f"⚠️ Could not fetch manga details for URL detection: {e}")
    return jsonify(result)

@manga_bp.route('/discover')
@limit_medium
def get_discover():
    """Get hidden gems - lesser-known but high-quality manga for discovery."""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
        if limit < 1 or limit > 25:
            return jsonify({'error': 'Limit must be between 1 and 25'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid parameters'}), 400

    log(f"💎 Loading hidden gems from Jikan (page {page})...")
    jikan = get_jikan_client()
    results = jikan.get_hidden_gems(limit=limit, page=page)

    return jsonify(results)

@manga_bp.route('/popular')
@limit_medium
def get_popular():
    """Get popular manga - blended mix of trending and all-time top."""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
        if limit < 1 or limit > 25:
            return jsonify({'error': 'Limit must be between 1 and 25'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid parameters'}), 400

    log(f"📚 Loading blended popular manga from Jikan (page {page})...")
    jikan = get_jikan_client()
    results = jikan.get_blended_popular(limit=limit, page=page)

    return jsonify(results)

@manga_bp.route('/trending')
@limit_medium
def get_trending():
    """Get trending/seasonal manga from Jikan."""
    try:
        limit = int(request.args.get('limit', 20))
        page = int(request.args.get('page', 1))
        if limit < 1 or limit > 25:
            return jsonify({'error': 'Limit must be between 1 and 25'}), 400
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid parameters'}), 400

    log(f"🔥 Loading trending manga from Jikan (page {page})...")
    jikan = get_jikan_client()
    # Seasonal feed sometimes returns limited items; fall back to top list for variety
    results = jikan.get_seasonal_manga(limit=limit, page=page) or jikan.get_top_manga(limit=limit, page=page)

    return jsonify(results)

@manga_bp.route('/recommendations/<int:mal_id>')
def get_recommendations(mal_id):
    """Get manga recommendations based on a specific manga's MAL ID."""
    try:
        limit = int(request.args.get('limit', 8))
        if limit < 1 or limit > 20:
            return jsonify({'error': 'Limit must be between 1 and 20'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid limit parameter'}), 400

    if mal_id < 1:
        return jsonify({'error': 'Invalid MAL ID'}), 400

    log(f"🔗 Loading recommendations for MAL ID {mal_id}...")
    jikan = get_jikan_client()
    results = jikan.get_recommendations(mal_id, limit=limit)

    return jsonify(results)

@manga_bp.route('/latest')
def get_latest():
    """Get latest updated manga."""
    manager = get_source_manager()
    source_id = request.args.get('source_id')
    try:
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid page number'}), 400
    results = manager.get_latest(source_id, page)
    return jsonify([r.to_dict() for r in results])

@manga_bp.route('/latest_feed')
def get_latest_feed():
    """
    Discover feed: latest updates from sources with pagination.
    Mirrors /latest but kept separate to avoid breaking existing clients.
    """
    manager = get_source_manager()
    source_id = request.args.get('source_id')
    try:
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid page number'}), 400

    results = manager.get_latest(source_id, page)
    return jsonify([r.to_dict() for r in results])

@manga_bp.route('/chapters', methods=['POST'])
@csrf_protect
@limit_medium
def get_chapters():
    """
    Get chapters for a manga.

    If manga comes from Jikan (has mal_id but no source), automatically searches
    sources to find chapter availability.
    """
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    offset = data.get('offset', 0)
    limit = data.get('limit', 100)
    manga_title = data.get('title')
    mal_id = data.get('mal_id')
    manga_id = data.get('id')
    source_id = data.get('source')

    # If no source specified or it's a Jikan pseudo-source, try to auto-detect real source
    if (not source_id or source_id == 'jikan') and manga_title:
        log(f"🔍 Auto-detecting source for '{manga_title}'...")

        # Try to find this manga in our sources
        search_results = manager.search(manga_title, source_id=None)

        if search_results:
            # Use the first result (most relevant)
            best_match = search_results[0]
            manga_id = best_match.id
            source_id = best_match.source
            log(f"✅ Found in {source_id}: {best_match.title}")
        else:
            return jsonify({
                'error': 'Could not find this manga in any source',
                'message': 'Try searching for it manually in the source selector'
            }), 404

    if not manga_id or not source_id:
        return jsonify({'error': 'Missing id or source'}), 400

    try:
        chapters = manager.get_chapters(manga_id, source_id)

        # Auto-fallback: If source returns no chapters and we have a title, try other sources
        if not chapters and manga_title:
            log(f"⚠️ No chapters from {source_id}, trying fallback sources...")
            priority_sources = ['weebcentral-v2', 'mangadex', 'mangasee-v2', 'manganato-v2', 'mangafire', 'comicx']

            for fallback_source in priority_sources:
                if fallback_source == source_id:
                    continue  # Skip the source we already tried

                fallback_results = manager.search(manga_title, source_id=fallback_source)
                if fallback_results:
                    fallback_manga = fallback_results[0]
                    fallback_chapters = manager.get_chapters(fallback_manga.id, fallback_source)
                    if fallback_chapters:
                        log(f"✅ Found {len(fallback_chapters)} chapters in {fallback_source}")
                        chapters = fallback_chapters
                        manga_id = fallback_manga.id
                        source_id = fallback_source
                        break

        paginated = chapters[offset:offset + limit]

        return jsonify({
            'chapters': [c.to_dict() for c in paginated],
            'total': len(chapters),
            'hasMore': offset + limit < len(chapters),
            'nextOffset': offset + limit,
            'source_id': source_id,  # Return which source we used
            'manga_id': manga_id      # Return the source's manga ID
        })
    except Exception as e:
        log(f"❌ Failed to get chapters: {e}")
        return jsonify({'error': str(e)}), 500

@manga_bp.route('/chapter_pages', methods=['POST'])
@csrf_protect
@limit_medium
def get_chapter_pages():
    """Get page images for a chapter."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    log(f"📖 [READER API] Request data: {data}")

    error = validate_fields(data, [
        ('chapter_id', str, 500),
        ('source', str, 100)
    ])
    if error:
        log(f"❌ [READER API] Validation error: {error}")
        return jsonify({'error': error}), 400

    chapter_id = data['chapter_id']
    source_id = data['source']
    log(f"📖 [READER API] Fetching pages for chapter_id={chapter_id}, source={source_id}")

    pages = manager.get_pages(chapter_id, source_id)
    log(f"📖 [READER API] Got {len(pages) if pages else 0} pages from manager")

    if not pages:
        log(f"❌ [READER API] No pages returned from source {source_id}")
        return jsonify({'error': 'Failed to fetch pages'}), 500

    page_urls = [p.url for p in pages]
    log(f"✅ [READER API] Returning {len(page_urls)} page URLs")
    log(f"📖 [READER API] First page URL sample: {page_urls[0] if page_urls else 'N/A'}")

    return jsonify({
        'pages': page_urls,
        'pages_data': [p.to_dict() for p in pages]
    })

@manga_bp.route('/search/cache/stats')
def cache_stats():
    """
    Get search cache statistics.

    Returns:
        {
            "size": 42,           // Current number of cached entries
            "max_size": 1000,     // Maximum capacity
            "ttl": 3600,          // TTL in seconds
            "hits": 156,          // Number of cache hits
            "misses": 89,         // Number of cache misses
            "hit_rate": 63.67     // Hit rate percentage
        }
    """
    return jsonify(_smart_search.cache.stats())

@manga_bp.route('/search/cache/clear', methods=['POST'])
@csrf_protect
def clear_cache():
    """
    Clear all search cache entries.

    Useful for testing or forcing fresh searches.

    Returns:
        {"status": "ok", "message": "Cache cleared"}
    """
    _smart_search.cache.clear()
    log("🗑️ Search cache cleared")
    return jsonify({'status': 'ok', 'message': 'Cache cleared'})

@manga_bp.route('/all_chapters', methods=['POST'])
@csrf_protect
def get_all_chapters():
    """Get all chapters for a manga (no pagination)."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('id', str, 500),
        ('source', str, 100)
    ])
    if error:
        return jsonify({'error': error}), 400
    manga_id = data['id']
    source_id = data['source']
    chapters = manager.get_chapters(manga_id, source_id)
    return jsonify({
        'chapters': [c.to_dict() for c in chapters],
        'total': len(chapters)
    })

@manga_bp.route('/search/cache/evict', methods=['POST'])
@csrf_protect
def evict_expired():
    """
    Manually evict expired cache entries.

    Normally handled automatically, but useful for cleanup.

    Returns:
        {"status": "ok", "evicted": 5}
    """
    evicted = _smart_search.cache.evict_expired()
    log(f"🗑️ Evicted {evicted} expired cache entries")
    return jsonify({'status': 'ok', 'evicted': evicted})

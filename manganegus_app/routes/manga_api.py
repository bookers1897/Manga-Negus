from flask import Blueprint, jsonify, request
import asyncio
from sources import get_source_manager
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.search.smart_search import SmartSearch

manga_bp = Blueprint('manga_api', __name__, url_prefix='/api')

# Initialize smart search
_smart_search = SmartSearch()

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
def search():
    """Search for manga."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    query = data.get('query', '')
    source_id = data.get('source_id')
    if not query:
        return jsonify([])
    results = manager.search(query, source_id)
    return jsonify([r.to_dict() for r in results])

@manga_bp.route('/search/smart', methods=['POST'])
@csrf_protect
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
def detect_url():
    """Detect source and manga ID from a URL."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
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

@manga_bp.route('/popular')
def get_popular():
    """Get popular manga."""
    manager = get_source_manager()
    source_id = request.args.get('source_id')
    try:
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid page number'}), 400
    results = manager.get_popular(source_id, page)
    return jsonify([r.to_dict() for r in results])

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

@manga_bp.route('/chapters', methods=['POST'])
@csrf_protect
def get_chapters():
    """Get chapters for a manga."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    manga_id = data.get('id')
    source_id = data.get('source')
    offset = data.get('offset', 0)
    limit = data.get('limit', 100)
    if not manga_id or not source_id:
        return jsonify({'error': 'Missing id or source'}), 400
    chapters = manager.get_chapters(manga_id, source_id)
    paginated = chapters[offset:offset + limit]
    return jsonify({
        'chapters': [c.to_dict() for c in paginated],
        'total': len(chapters),
        'hasMore': offset + limit < len(chapters),
        'nextOffset': offset + limit
    })

@manga_bp.route('/chapter_pages', methods=['POST'])
@csrf_protect
def get_chapter_pages():
    """Get page images for a chapter."""
    manager = get_source_manager()
    data = request.get_json(silent=True) or {}
    chapter_id = data.get('chapter_id')
    source_id = data.get('source')
    if not chapter_id or not source_id:
        return jsonify({'error': 'Missing chapter_id or source'}), 400
    pages = manager.get_pages(chapter_id, source_id)
    if not pages:
        return jsonify({'error': 'Failed to fetch pages'}), 500
    return jsonify({
        'pages': [p.url for p in pages],
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
    manga_id = data.get('id')
    source_id = data.get('source')
    if not manga_id or not source_id:
        return jsonify({'error': 'Missing id or source'}), 400
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

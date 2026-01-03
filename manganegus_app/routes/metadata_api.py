"""
================================================================================
MangaNegus v3.1 - Metadata API Routes
================================================================================
Flask blueprint for metadata aggregation endpoints.

NEW ENDPOINTS:
  GET  /api/metadata/providers      - List available metadata providers
  POST /api/metadata/search          - Search across all providers
  POST /api/metadata/enrich          - Get enriched metadata for manga
  GET  /api/metadata/health          - Health check for all providers
  POST /api/metadata/resolve-ids     - Resolve external API IDs

These endpoints power the MetaForge metadata integration system.
================================================================================
"""

from flask import Blueprint, jsonify, request
import asyncio
import logging

# Import metadata manager
from ..metadata.manager import get_metadata_manager
from ..csrf import csrf_protect

logger = logging.getLogger(__name__)

# Create blueprint
metadata_api_bp = Blueprint('metadata_api', __name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_async(coro):
    """
    Run async coroutine in sync Flask context.

    Flask routes are sync, but our metadata system is async.
    This helper bridges the gap.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


# =============================================================================
# METADATA ROUTES
# =============================================================================

@metadata_api_bp.route('/api/metadata/providers', methods=['GET'])
def get_providers():
    """
    Get list of available metadata providers.

    Returns:
        {
            "providers": [
                {
                    "id": "anilist",
                    "name": "AniList",
                    "rate_limit": 90,
                    "status": "active"
                },
                ...
            ]
        }
    """
    try:
        async def _get_providers():
            manager = await get_metadata_manager()
            provider_ids = manager.get_available_providers()

            providers_info = []
            for provider_id in provider_ids:
                provider = manager.providers[provider_id]
                providers_info.append({
                    'id': provider.id,
                    'name': provider.name,
                    'rate_limit': provider.rate_limit,
                    'base_url': provider.base_url,
                    'status': 'active'
                })

            return providers_info

        providers = run_async(_get_providers())

        return jsonify({
            'providers': providers,
            'count': len(providers)
        })

    except Exception as e:
        logger.error(f"Get providers failed: {e}")
        return jsonify({'error': str(e)}), 500


@metadata_api_bp.route('/api/metadata/search', methods=['POST'])
@csrf_protect
def search_metadata():
    """
    Search for manga across all metadata providers.

    Request:
        {
            "title": "One Piece",
            "limit": 10,
            "providers": ["anilist", "mal"]  // optional
        }

    Returns:
        {
            "results": [
                {
                    "negus_id": "anilist:30013",
                    "titles": {"en": "One Piece", ...},
                    "mappings": {"anilist": "30013", "mal": "21"},
                    "rating": 8.5,
                    "synopsis": "...",
                    ...
                }
            ],
            "count": 10,
            "providers_used": ["anilist", "mal"]
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title')
        limit = data.get('limit', 10)
        providers = data.get('providers')  # Optional

        if not title:
            return jsonify({'error': 'Title required'}), 400

        async def _search():
            manager = await get_metadata_manager()
            results = await manager.search(title, limit, providers)

            # Convert to dict for JSON
            return [result.to_dict() for result in results]

        results = run_async(_search())

        return jsonify({
            'results': results,
            'count': len(results),
            'providers_used': providers or 'all'
        })

    except Exception as e:
        logger.error(f"Metadata search failed: {e}")
        return jsonify({'error': str(e)}), 500


@metadata_api_bp.route('/api/metadata/enrich', methods=['POST'])
@csrf_protect
def enrich_metadata():
    """
    Get enriched metadata for a manga.

    This is the main MetaForge operation - searches all providers,
    finds matches, and merges the data.

    Request:
        {
            "title": "One Piece",
            "source_id": "mangadex",       // optional
            "source_manga_id": "a1c7c817..." // optional
        }

    Returns:
        {
            "metadata": {
                "negus_id": "anilist:30013",
                "titles": {"en": "One Piece", "ja": "ワンピース", ...},
                "mappings": {
                    "anilist": "30013",
                    "mal": "21",
                    "kitsu": "42765",
                    "shikimori": "42765",
                    "mangaupdates": "61"
                },
                "rating": 8.82,              // Weighted average
                "rating_anilist": 87,
                "rating_mal": 9.0,
                "rating_kitsu": 85.5,
                "genres": ["Action", "Adventure", "Comedy", ...],
                "tags": ["Pirates", "Superpowers", ...],
                "synopsis": "...",
                "cover_image": "https://...",
                "banner_image": "https://...",
                "chapters": 1090,
                "volumes": 104,
                "status": "releasing",
                "year": 1997,
                ...
            },
            "sources_merged": 5,
            "cache_ttl": 86400
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title')
        source_id = data.get('source_id')
        source_manga_id = data.get('source_manga_id')

        if not title:
            return jsonify({'error': 'Title required'}), 400

        async def _enrich():
            manager = await get_metadata_manager()
            metadata = await manager.get_enriched_metadata(
                title,
                source_id,
                source_manga_id
            )
            return metadata

        metadata = run_async(_enrich())

        if not metadata:
            return jsonify({
                'error': 'No metadata found',
                'title': title
            }), 404

        # Get cache TTL from provider
        manager = run_async(get_metadata_manager())
        anilist = manager.providers.get('anilist')
        cache_ttl = anilist.get_cache_ttl(metadata) if anilist else 86400

        return jsonify({
            'metadata': metadata.to_dict(),
            'sources_merged': len(metadata.mappings),
            'cache_ttl': cache_ttl
        })

    except Exception as e:
        logger.error(f"Metadata enrichment failed: {e}")
        return jsonify({'error': str(e)}), 500


@metadata_api_bp.route('/api/metadata/by-id', methods=['POST'])
@csrf_protect
def get_by_id():
    """
    Get metadata from specific provider by ID.

    Request:
        {
            "provider": "anilist",
            "id": "30013"
        }

    Returns:
        {
            "metadata": {...}
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        provider_id = data.get('provider')
        manga_id = data.get('id')

        if not provider_id or not manga_id:
            return jsonify({'error': 'Provider and ID required'}), 400

        async def _get_by_id():
            manager = await get_metadata_manager()
            return await manager.get_by_id(provider_id, manga_id)

        metadata = run_async(_get_by_id())

        if not metadata:
            return jsonify({
                'error': 'Not found',
                'provider': provider_id,
                'id': manga_id
            }), 404

        return jsonify({
            'metadata': metadata.to_dict()
        })

    except Exception as e:
        logger.error(f"Get by ID failed: {e}")
        return jsonify({'error': str(e)}), 500


@metadata_api_bp.route('/api/metadata/health', methods=['GET'])
def health_check():
    """
    Check health of all metadata providers.

    Returns:
        {
            "healthy": true,
            "providers": {
                "anilist": true,
                "mal": true,
                "kitsu": false,
                ...
            },
            "healthy_count": 4,
            "total_count": 5
        }
    """
    try:
        async def _health_check():
            manager = await get_metadata_manager()
            return await manager.health_check()

        health = run_async(_health_check())

        healthy_count = sum(1 for status in health.values() if status)
        total_count = len(health)

        return jsonify({
            'healthy': healthy_count > 0,
            'providers': health,
            'healthy_count': healthy_count,
            'total_count': total_count
        })

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'error': str(e)}), 500


@metadata_api_bp.route('/api/metadata/batch-enrich', methods=['POST'])
@csrf_protect
def batch_enrich():
    """
    Enrich metadata for multiple manga in parallel.

    This is used by the frontend to enrich search results cards
    without blocking the UI.

    Request:
        {
            "manga": [
                {"title": "One Piece", "source_id": "mangadex", "source_manga_id": "..."},
                {"title": "Naruto", "source_id": "mangadex", "source_manga_id": "..."},
                ...
            ],
            "limit": 10  // Max manga to process
        }

    Returns:
        {
            "results": [
                {
                    "title": "One Piece",
                    "metadata": {...},
                    "success": true
                },
                {
                    "title": "Naruto",
                    "error": "Not found",
                    "success": false
                },
                ...
            ],
            "success_count": 8,
            "total_count": 10
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        manga_list = data.get('manga', [])
        limit = min(data.get('limit', 10), 20)  # Cap at 20 to prevent abuse

        if not manga_list:
            return jsonify({'error': 'Manga list required'}), 400

        # Limit to prevent overload
        manga_list = manga_list[:limit]

        async def _batch_enrich():
            manager = await get_metadata_manager()

            results = []
            for manga_info in manga_list:
                title = manga_info.get('title')
                source_id = manga_info.get('source_id')
                source_manga_id = manga_info.get('source_manga_id')

                try:
                    metadata = await manager.get_enriched_metadata(
                        title, source_id, source_manga_id
                    )

                    if metadata:
                        results.append({
                            'title': title,
                            'metadata': metadata.to_dict(),
                            'success': True
                        })
                    else:
                        results.append({
                            'title': title,
                            'error': 'Not found',
                            'success': False
                        })

                except Exception as e:
                    logger.error(f"Batch enrich failed for '{title}': {e}")
                    results.append({
                        'title': title,
                        'error': str(e),
                        'success': False
                    })

            return results

        results = run_async(_batch_enrich())

        success_count = sum(1 for r in results if r['success'])

        return jsonify({
            'results': results,
            'success_count': success_count,
            'total_count': len(results)
        })

    except Exception as e:
        logger.error(f"Batch enrich failed: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@metadata_api_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@metadata_api_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

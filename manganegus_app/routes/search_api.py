"""Advanced Search API Blueprint.

Provides endpoints for complex filtering and searching of the manga library.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, g
from sqlalchemy import or_, cast, String, asc, desc

from manganegus_app.cache import global_cache
from manganegus_app.csrf import csrf_protect
from manganegus_app.database import get_db_session
from manganegus_app.log import log
from manganegus_app.models import Series, SourceLink, SearchCache, User
from manganegus_app.rate_limit import limit_heavy, limit_light
from .auth_api import login_required
from .validators import sanitize_string


search_bp = Blueprint('search_api', __name__, url_prefix='/api/search')
search_legacy_bp = Blueprint('search_legacy_api', __name__, url_prefix='/api/manga')

CACHE_TTL_SECONDS = 20 * 60
CACHE_PREFIX = 'search:advanced'

SORT_FIELDS = {
    'updated_at': Series.updated_at,
    'created_at': Series.created_at,
    'title': Series.title,
    'year': Series.year,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, detail: Optional[str] = None, code: str = 'invalid_request', status: int = 400):
    payload = {'error': message, 'code': code}
    if detail:
        payload['detail'] = detail
    return jsonify(payload), status


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _make_cache_key(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _cache_get(cache_key: str) -> Optional[Dict[str, Any]]:
    cached = global_cache.get_json(f"{CACHE_PREFIX}:{cache_key}")
    if cached:
        return cached

    try:
        with get_db_session() as session:
            entry = session.query(SearchCache).filter_by(key=cache_key).first()
            if entry and entry.expires_at > datetime.now(timezone.utc):
                global_cache.set_json(f"{CACHE_PREFIX}:{cache_key}", entry.data, ttl=CACHE_TTL_SECONDS)
                return entry.data
            if entry:
                session.delete(entry)
    except Exception as exc:
        log(f"Search cache DB read failed: {exc}")

    return None


def _cache_set(cache_key: str, payload: Dict[str, Any]) -> None:
    global_cache.set_json(f"{CACHE_PREFIX}:{cache_key}", payload, ttl=CACHE_TTL_SECONDS)
    try:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL_SECONDS)
        with get_db_session() as session:
            session.merge(SearchCache(
                key=cache_key,
                data=payload,
                expires_at=expires_at
            ))
    except Exception as exc:
        log(f"Search cache DB write failed: {exc}")


def _current_user_id() -> Optional[str]:
    user = getattr(g, 'current_user', None)
    if user and getattr(user, 'is_authenticated', False):
        return str(getattr(user, 'id', ''))
    return None


def _record_search_history(payload: Dict[str, Any]) -> None:
    user_id = _current_user_id()
    if not user_id:
        return
    try:
        with get_db_session() as session:
            user = session.query(User).get(user_id)
            if not user:
                return
            prefs = user.preferences or {}
            history = prefs.get('search_history', [])
            if not isinstance(history, list):
                history = []
            entry = {
                'query': payload.get('search_term', ''),
                'filters': {
                    'genres': payload.get('genres', []),
                    'status': payload.get('status', []),
                    'min_rating': payload.get('min_rating'),
                    'year_from': payload.get('year_from'),
                    'year_to': payload.get('year_to'),
                    'min_chapters': payload.get('min_chapters'),
                    'sort_by': payload.get('sort_by'),
                    'sort_order': payload.get('sort_order'),
                    'recently_updated': payload.get('recently_updated')
                },
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            entry_key = json.dumps(
                {'query': entry['query'], 'filters': entry['filters']},
                sort_keys=True,
                separators=(',', ':')
            )
            filtered = []
            for item in history:
                item_key = json.dumps(
                    {
                        'query': item.get('query', ''),
                        'filters': item.get('filters', {})
                    },
                    sort_keys=True,
                    separators=(',', ':')
                )
                if item_key != entry_key:
                    filtered.append(item)
            filtered.insert(0, entry)
            prefs['search_history'] = filtered[:20]
            user.preferences = prefs
            session.add(user)
    except Exception as exc:
        log(f"Search history update failed: {exc}")


def _apply_sort(query, sort_by: str, sort_order: str):
    column = SORT_FIELDS.get(sort_by)
    if not column:
        return None
    if sort_order == 'asc':
        return query.order_by(asc(column))
    return query.order_by(desc(column))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@search_bp.route('/advanced', methods=['POST'])
@search_legacy_bp.route('/advanced', methods=['POST'])
@csrf_protect
@limit_heavy
def advanced_search():
    """
    Perform an advanced search with multiple filters.

    Payload:
    {
        "search_term": str,
        "genres": [str],        # List of genre names (AND logic)
        "status": [str],        # List of statuses (OR logic)
        "year_from": int,
        "year_to": int,
        "min_rating": float,
        "min_chapters": int,
        "recently_updated": bool,
        "sort_by": str,         # 'updated_at', 'title', 'year', 'created_at'
        "sort_order": str,      # 'asc', 'desc'
        "page": int,
        "per_page": int
    }
    """
    data = request.get_json(silent=True) or {}

    page_raw = data.get('page', 1)
    per_page_raw = data.get('per_page', data.get('limit', 20))
    sort_by = (data.get('sort_by') or 'updated_at').strip()
    sort_order = (data.get('sort_order') or 'desc').strip().lower()

    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        return _error('Invalid page', detail='page must be an integer')
    if page < 1:
        return _error('Invalid page', detail='page must be >= 1')

    try:
        per_page = int(per_page_raw)
    except (TypeError, ValueError):
        return _error('Invalid per_page', detail='per_page must be an integer')
    if per_page < 1:
        return _error('Invalid per_page', detail='per_page must be >= 1')
    per_page = min(per_page, 50)

    if sort_by not in SORT_FIELDS:
        return _error('Invalid sort_by', detail=f"Supported values: {', '.join(sorted(SORT_FIELDS.keys()))}")
    if sort_order not in ('asc', 'desc'):
        return _error('Invalid sort_order', detail='sort_order must be asc or desc')

    search_term = sanitize_string(data.get('search_term') or data.get('query') or '', max_length=200).strip()
    author = sanitize_string(data.get('author') or '', max_length=200).strip()
    artist = sanitize_string(data.get('artist') or '', max_length=200).strip()

    genres = data.get('genres')
    if genres is not None and not isinstance(genres, list):
        return _error('Invalid genres', detail='genres must be a list')
    genres = _coerce_list(genres)

    statuses = data.get('status')
    if statuses is not None and not isinstance(statuses, list):
        return _error('Invalid status', detail='status must be a list')
    statuses = _coerce_list(statuses)

    year_from = data.get('year_from')
    year_to = data.get('year_to')
    min_chapters = data.get('min_chapters')
    min_rating = data.get('min_rating')
    recently_updated = bool(data.get('recently_updated')) if data.get('recently_updated') is not None else False

    if year_from not in (None, ''):
        try:
            year_from = int(year_from)
        except (TypeError, ValueError):
            return _error('Invalid year_from', detail='year_from must be an integer')
    else:
        year_from = None

    if year_to not in (None, ''):
        try:
            year_to = int(year_to)
        except (TypeError, ValueError):
            return _error('Invalid year_to', detail='year_to must be an integer')
    else:
        year_to = None

    if year_from and year_to and year_from > year_to:
        return _error('Invalid year range', detail='year_from cannot be greater than year_to')

    if min_chapters not in (None, ''):
        try:
            min_chapters = int(min_chapters)
        except (TypeError, ValueError):
            return _error('Invalid min_chapters', detail='min_chapters must be an integer')
    else:
        min_chapters = None

    if min_rating not in (None, ''):
        try:
            min_rating = float(min_rating)
        except (TypeError, ValueError):
            return _error('Invalid min_rating', detail='min_rating must be a number')
    else:
        min_rating = None

    cache_payload = {
        'search_term': search_term,
        'author': author,
        'artist': artist,
        'genres': [str(g).strip() for g in genres if g not in (None, '')],
        'status': [str(s).strip() for s in statuses if s not in (None, '')],
        'year_from': year_from,
        'year_to': year_to,
        'min_chapters': min_chapters,
        'min_rating': min_rating,
        'recently_updated': recently_updated,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'page': page,
        'per_page': per_page,
    }
    cache_key = _make_cache_key(cache_payload)

    cached = _cache_get(cache_key)
    if cached:
        _record_search_history(cache_payload)
        return jsonify(cached)

    try:
        with get_db_session() as db:
            query = db.query(Series)

            # Text search across title/author/description
            if search_term:
                like_term = f"%{search_term}%"
                query = query.filter(
                    or_(
                        Series.title.ilike(like_term),
                        Series.author.ilike(like_term),
                        Series.description.ilike(like_term)
                    )
                )

            if author:
                query = query.filter(Series.author.ilike(f"%{author}%"))
            if artist:
                query = query.filter(Series.artist.ilike(f"%{artist}%"))

            # Genres (AND logic)
            for genre in genres:
                if genre:
                    query = query.filter(cast(Series.genres, String).ilike(f'%"{genre}"%'))

            # Status (OR logic)
            if statuses:
                query = query.filter(Series.status.in_([s for s in statuses if s]))

            # Year range
            if year_from:
                query = query.filter(Series.year >= year_from)
            if year_to:
                query = query.filter(Series.year <= year_to)

            # Min chapters
            if min_chapters:
                query = query.join(Series.source_links).filter(SourceLink.chapters_count >= min_chapters)
                query = query.distinct(Series.id)

            # Min rating (only if column exists)
            rating_column = getattr(Series, 'rating_average', None) or getattr(Series, 'rating', None)
            if min_rating is not None:
                if rating_column is None:
                    return _error('Unsupported filter', detail='Rating filter is not available', code='unsupported_filter')
                query = query.filter(rating_column >= min_rating)

            # Recently updated (last 7 days)
            if recently_updated:
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                query = query.filter(Series.updated_at >= cutoff)

            sorted_query = _apply_sort(query, sort_by, sort_order)
            if sorted_query is None:
                return _error('Invalid sort_by', detail='Unsupported sort column')
            query = sorted_query

            total = query.count()
            items = query.offset((page - 1) * per_page).limit(per_page).all()

            results = []
            for series in items:
                max_chapters = 0
                if series.source_links:
                    max_chapters = max((sl.chapters_count for sl in series.source_links if sl.chapters_count), default=0)
                results.append({
                    'id': series.id,
                    'title': series.title,
                    'slug': series.slug,
                    'cover_image': series.cover_image,
                    'author': series.author,
                    'artist': series.artist,
                    'status': series.status,
                    'year': series.year,
                    'genres': series.genres,
                    'updated_at': series.updated_at.isoformat() if series.updated_at else None,
                    'chapter_count': max_chapters,
                })

            payload = {
                'results': results,
                'total': total,
                'pages': math.ceil(total / per_page) if per_page else 0,
                'current_page': page
            }

            _cache_set(cache_key, payload)
            _record_search_history(cache_payload)

            return jsonify(payload)

    except Exception as exc:
        log(f"Advanced search failed: {exc}")
        return _error('Search failed', detail='Unexpected server error', code='server_error', status=500)


@search_bp.route('/genres', methods=['GET'])
@search_legacy_bp.route('/genres', methods=['GET'])
@limit_light
def get_genres():
    """Return available genres based on stored series metadata."""
    try:
        with get_db_session() as db:
            rows = db.query(Series.genres).filter(Series.genres.isnot(None)).all()
        genres: set[str] = set()
        for row in rows:
            if not row:
                continue
            value = row[0]
            if isinstance(value, list):
                for item in value:
                    if item:
                        genres.add(str(item))
        return jsonify({'genres': sorted(genres)})
    except Exception as exc:
        log(f"Genre lookup failed: {exc}")
        return _error('Genre lookup failed', detail='Unexpected server error', code='server_error', status=500)


@search_bp.route('/authors', methods=['GET'])
@search_legacy_bp.route('/authors', methods=['GET'])
@limit_light
def get_authors():
    """Return author suggestions. Optional query param: ?q=term"""
    q = sanitize_string(request.args.get('q', ''), max_length=200).strip()
    limit_raw = request.args.get('limit', 20)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        return _error('Invalid limit', detail='limit must be an integer')
    limit = max(1, min(limit, 50))

    try:
        with get_db_session() as db:
            query = db.query(Series.author).filter(Series.author.isnot(None))
            if q:
                query = query.filter(Series.author.ilike(f"%{q}%"))
            rows = query.order_by(Series.author.asc()).limit(limit).all()
        authors = [row[0] for row in rows if row and row[0]]
        return jsonify({'authors': authors})
    except Exception as exc:
        log(f"Author lookup failed: {exc}")
        return _error('Author lookup failed', detail='Unexpected server error', code='server_error', status=500)


@search_bp.route('/history', methods=['GET'])
@search_legacy_bp.route('/history', methods=['GET'])
@login_required
@limit_light
def get_search_history():
    """Return search history for the current user."""
    user_id = _current_user_id()
    if not user_id:
        return _error('Unauthorized', detail='Login required', code='unauthorized', status=401)
    try:
        with get_db_session() as db:
            user = db.query(User).get(user_id)
            prefs = user.preferences if user else {}
            history = prefs.get('search_history', []) if isinstance(prefs, dict) else []
        return jsonify({'history': history})
    except Exception as exc:
        log(f"Search history fetch failed: {exc}")
        return _error('History lookup failed', detail='Unexpected server error', code='server_error', status=500)

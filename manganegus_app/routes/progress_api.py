"""
================================================================================
MangaNegus v4.0 - Reading Progress API (NEG-16, NEG-32, NEG-33)
================================================================================
Tracks per-chapter reading progress and provides "continue reading" functionality.

Endpoints:
    POST /api/progress/save       - Save reading position
    GET  /api/progress/manga/<id> - Get progress for specific manga
    GET  /api/progress/chapter/<id> - Get progress for specific chapter
    GET  /api/progress/history    - Get reading history timeline
    GET  /api/progress/continue   - Get list of manga to continue reading

================================================================================
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from sqlalchemy import desc, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from manganegus_app.csrf import csrf_protect
from manganegus_app.database import get_db_session
from manganegus_app.models import ReadingProgress, ReadingHistory, SourceLink
from manganegus_app.log import log
from .auth_api import login_required, optional_login
from .validators import validate_fields

progress_bp = Blueprint('progress', __name__, url_prefix='/api/progress')


@progress_bp.route('/save', methods=['POST'])
@optional_login
@csrf_protect
def save_progress():
    """
    Save reading position for a chapter.

    Request body:
        {
            "manga_id": "source:manga_id",  # or just manga_id with source separate
            "source": "mangadex",           # optional if manga_id has source prefix
            "chapter_id": "chapter-uuid",
            "chapter_number": "1",          # optional
            "current_page": 5,
            "total_pages": 20,
            "is_completed": false,          # optional
            "manga_title": "One Piece",     # optional, for history
            "manga_cover": "https://...",   # optional, for history
            "chapter_title": "Chapter 1"    # optional, for history
        }

    Returns:
        {"success": true, "progress_id": "..."}
    """
    data = request.get_json(silent=True) or {}

    # Validate required fields
    manga_id_raw = data.get('manga_id')
    chapter_id = data.get('chapter_id')
    current_page = data.get('current_page', 1)

    if not manga_id_raw or not chapter_id:
        return jsonify({'error': 'Missing required fields: manga_id, chapter_id'}), 400

    # Parse manga_id - could be "source:id" or just "id" with separate source
    source_id = data.get('source')
    manga_id = manga_id_raw

    if ':' in manga_id_raw and not source_id:
        parts = manga_id_raw.split(':', 1)
        if len(parts) == 2:
            source_id, manga_id = parts

    if not source_id:
        return jsonify({'error': 'Missing source_id (provide source or use source:manga_id format)'}), 400

    # Normalize manga_id format
    full_manga_id = f"{source_id}:{manga_id}"

    # Get user_id if logged in
    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    try:
        current_page = int(current_page)
    except (ValueError, TypeError):
        current_page = 1

    total_pages = data.get('total_pages')
    if total_pages is not None:
        try:
            total_pages = int(total_pages)
        except (ValueError, TypeError):
            total_pages = None

    is_completed = data.get('is_completed', False)
    if total_pages and current_page >= total_pages:
        is_completed = True

    chapter_number = data.get('chapter_number') or data.get('chapter_num')

    try:
        with get_db_session() as session:
            now = datetime.now(timezone.utc)

            # Try to find existing progress record
            existing = session.query(ReadingProgress).filter(
                and_(
                    ReadingProgress.user_id == user_id,
                    ReadingProgress.manga_id == full_manga_id,
                    ReadingProgress.chapter_id == str(chapter_id)
                )
            ).first()

            if existing:
                # Update existing record
                existing.current_page = current_page
                if total_pages:
                    existing.total_pages = total_pages
                existing.is_completed = is_completed
                existing.last_read_at = now
                if chapter_number:
                    existing.chapter_number = str(chapter_number)
                progress_id = existing.id
            else:
                # Create new progress record
                import uuid
                progress = ReadingProgress(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    manga_id=full_manga_id,
                    source_id=source_id,
                    chapter_id=str(chapter_id),
                    chapter_number=str(chapter_number) if chapter_number else None,
                    current_page=current_page,
                    total_pages=total_pages,
                    is_completed=is_completed,
                    last_read_at=now
                )
                session.add(progress)
                session.flush()
                progress_id = progress.id

            # Also log to reading history if significant progress or completed
            if is_completed or current_page > 1:
                _log_to_history(
                    session,
                    user_id=user_id,
                    manga_id=full_manga_id,
                    source_id=source_id,
                    chapter_id=str(chapter_id),
                    chapter_num=str(chapter_number) if chapter_number else None,
                    manga_title=data.get('manga_title'),
                    manga_cover=data.get('manga_cover'),
                    chapter_title=data.get('chapter_title'),
                    pages_read=current_page,
                    total_pages=total_pages
                )

            log(f"Progress saved: {full_manga_id} Ch{chapter_number} p{current_page}/{total_pages or '?'}")
            return jsonify({'success': True, 'progress_id': progress_id})

    except Exception as e:
        log(f"Error saving progress: {e}")
        return jsonify({'error': 'Failed to save progress'}), 500


def _log_to_history(session, user_id, manga_id, source_id, chapter_id, chapter_num,
                   manga_title=None, manga_cover=None, chapter_title=None,
                   pages_read=0, total_pages=None):
    """Log reading activity to history. Updates existing entry if same chapter read recently."""
    import uuid
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=1)

    # Check for recent history entry for same chapter (avoid spam)
    existing = session.query(ReadingHistory).filter(
        and_(
            ReadingHistory.user_id == user_id,
            ReadingHistory.manga_id == manga_id,
            ReadingHistory.chapter_id == chapter_id,
            ReadingHistory.read_at > recent_cutoff
        )
    ).first()

    if existing:
        # Update existing recent entry
        existing.pages_read = max(existing.pages_read or 0, pages_read or 0)
        if total_pages:
            existing.total_pages = total_pages
        existing.read_at = now
    else:
        # Create new history entry
        history = ReadingHistory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            manga_id=manga_id,
            source_id=source_id,
            manga_title=manga_title,
            manga_cover=manga_cover,
            chapter_id=chapter_id,
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            pages_read=pages_read,
            total_pages=total_pages,
            read_at=now
        )
        session.add(history)


@progress_bp.route('/manga/<path:manga_id>', methods=['GET'])
@optional_login
def get_manga_progress(manga_id):
    """
    Get all chapter progress for a specific manga.

    Args:
        manga_id: The manga ID (can be "source:id" format or just id)

    Query params:
        source: Source ID (optional if manga_id includes source)

    Returns:
        {"chapters": [...], "last_chapter_id": "...", "total_chapters_read": N}
    """
    source_id = request.args.get('source')

    # Parse manga_id
    if ':' in manga_id and not source_id:
        parts = manga_id.split(':', 1)
        if len(parts) == 2:
            source_id, manga_id = parts

    full_manga_id = f"{source_id}:{manga_id}" if source_id else manga_id

    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    try:
        with get_db_session() as session:
            progress_records = session.query(ReadingProgress).filter(
                and_(
                    ReadingProgress.user_id == user_id,
                    ReadingProgress.manga_id == full_manga_id
                )
            ).order_by(desc(ReadingProgress.last_read_at)).all()

            chapters = [p.to_dict() for p in progress_records]

            # Find the most recently read chapter
            last_chapter = progress_records[0] if progress_records else None

            # Count completed chapters
            completed_count = sum(1 for p in progress_records if p.is_completed)

            return jsonify({
                'chapters': chapters,
                'last_chapter_id': last_chapter.chapter_id if last_chapter else None,
                'last_chapter_number': last_chapter.chapter_number if last_chapter else None,
                'last_page': last_chapter.current_page if last_chapter else None,
                'total_chapters_read': len(progress_records),
                'chapters_completed': completed_count
            })

    except Exception as e:
        log(f"Error getting manga progress: {e}")
        return jsonify({'error': 'Failed to get progress'}), 500


@progress_bp.route('/chapter/<path:chapter_id>', methods=['GET'])
@optional_login
def get_chapter_progress(chapter_id):
    """
    Get progress for a specific chapter.

    Args:
        chapter_id: The chapter ID

    Query params:
        manga_id: The manga ID (optional, for filtering)

    Returns:
        {"current_page": N, "total_pages": M, "is_completed": bool} or null
    """
    manga_id = request.args.get('manga_id')

    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    try:
        with get_db_session() as session:
            query = session.query(ReadingProgress).filter(
                and_(
                    ReadingProgress.user_id == user_id,
                    ReadingProgress.chapter_id == chapter_id
                )
            )

            if manga_id:
                query = query.filter(ReadingProgress.manga_id == manga_id)

            progress = query.first()

            if progress:
                return jsonify(progress.to_dict())
            else:
                return jsonify(None)

    except Exception as e:
        log(f"Error getting chapter progress: {e}")
        return jsonify({'error': 'Failed to get progress'}), 500


@progress_bp.route('/history', methods=['GET'])
@optional_login
def get_history():
    """
    Get reading history timeline.

    Query params:
        limit: Number of entries (default 20, max 100)
        offset: Pagination offset (default 0)
        manga_id: Filter by manga ID (optional)

    Returns:
        {"history": [...], "total": N, "has_more": bool}
    """
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
    except (ValueError, TypeError):
        limit = 20

    try:
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0

    manga_id_filter = request.args.get('manga_id')

    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    try:
        with get_db_session() as session:
            query = session.query(ReadingHistory).filter(
                ReadingHistory.user_id == user_id
            )

            if manga_id_filter:
                query = query.filter(ReadingHistory.manga_id == manga_id_filter)

            # Get total count
            total = query.count()

            # Get paginated results
            entries = query.order_by(desc(ReadingHistory.read_at)).offset(offset).limit(limit + 1).all()

            has_more = len(entries) > limit
            entries = entries[:limit]

            history = [e.to_dict() for e in entries]

            return jsonify({
                'history': history,
                'total': total,
                'has_more': has_more
            })

    except Exception as e:
        log(f"Error getting reading history: {e}")
        return jsonify({'error': 'Failed to get history'}), 500


@progress_bp.route('/continue', methods=['GET'])
@optional_login
def get_continue_reading():
    """
    Get list of manga to continue reading.
    Returns manga with in-progress chapters (not completed) sorted by last read.

    Query params:
        limit: Number of entries (default 10, max 50)

    Returns:
        {"continue": [...]}

    Each entry contains:
        - manga_id, source_id, manga_title, manga_cover
        - last_chapter_id, last_chapter_number, current_page, total_pages
        - last_read_at
    """
    try:
        limit = min(int(request.args.get('limit', 10)), 50)
    except (ValueError, TypeError):
        limit = 10

    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    if not user_id:
        return jsonify({'continue': []})

    try:
        with get_db_session() as session:
            from sqlalchemy import func
            from sqlalchemy.orm import aliased

            # Get the most recent progress entry for each manga
            # Using a subquery to get max last_read_at per manga_id
            subquery = session.query(
                ReadingProgress.manga_id,
                func.max(ReadingProgress.last_read_at).label('max_read_at')
            ).filter(
                ReadingProgress.user_id == user_id
            ).group_by(ReadingProgress.manga_id).subquery()

            # Join with progress table to get full records
            progress_entries = session.query(ReadingProgress).join(
                subquery,
                and_(
                    ReadingProgress.manga_id == subquery.c.manga_id,
                    ReadingProgress.last_read_at == subquery.c.max_read_at
                )
            ).filter(
                ReadingProgress.user_id == user_id,
                ReadingProgress.is_completed == False  # Only in-progress manga
            ).order_by(desc(ReadingProgress.last_read_at)).limit(limit).all()

            # Enrich with manga metadata from history or source_links
            continue_list = []
            for progress in progress_entries:
                # Try to get title/cover from recent history
                history_entry = session.query(ReadingHistory).filter(
                    and_(
                        ReadingHistory.user_id == user_id,
                        ReadingHistory.manga_id == progress.manga_id
                    )
                ).order_by(desc(ReadingHistory.read_at)).first()

                manga_title = None
                manga_cover = None

                if history_entry:
                    manga_title = history_entry.manga_title
                    manga_cover = history_entry.manga_cover

                # Fallback: try source_links table
                if not manga_title:
                    source_link = session.query(SourceLink).filter(
                        and_(
                            SourceLink.source_id == progress.source_id,
                            SourceLink.source_manga_id == progress.manga_id.split(':', 1)[-1]
                        )
                    ).first()
                    if source_link:
                        manga_title = source_link.title
                        manga_cover = source_link.cover_image

                continue_list.append({
                    'manga_id': progress.manga_id,
                    'source_id': progress.source_id,
                    'manga_title': manga_title,
                    'manga_cover': manga_cover,
                    'last_chapter_id': progress.chapter_id,
                    'last_chapter_number': progress.chapter_number,
                    'current_page': progress.current_page,
                    'total_pages': progress.total_pages,
                    'last_read_at': progress.last_read_at.isoformat() if progress.last_read_at else None
                })

            return jsonify({'continue': continue_list})

    except Exception as e:
        log(f"Error getting continue reading: {e}")
        return jsonify({'error': 'Failed to get continue reading list'}), 500


@progress_bp.route('/mark-read', methods=['POST'])
@optional_login
@csrf_protect
def mark_chapter_read():
    """
    Mark a chapter as fully read (completed).

    Request body:
        {
            "manga_id": "source:manga_id",
            "chapter_id": "chapter-uuid",
            "chapter_number": "1",
            "total_pages": 20,
            "manga_title": "...",
            "manga_cover": "..."
        }

    Returns:
        {"success": true}
    """
    data = request.get_json(silent=True) or {}

    manga_id_raw = data.get('manga_id')
    chapter_id = data.get('chapter_id')

    if not manga_id_raw or not chapter_id:
        return jsonify({'error': 'Missing required fields: manga_id, chapter_id'}), 400

    # Parse manga_id
    source_id = data.get('source')
    manga_id = manga_id_raw

    if ':' in manga_id_raw and not source_id:
        parts = manga_id_raw.split(':', 1)
        if len(parts) == 2:
            source_id, manga_id = parts

    if not source_id:
        return jsonify({'error': 'Missing source_id'}), 400

    full_manga_id = f"{source_id}:{manga_id}"

    user_id = None
    if hasattr(g, 'current_user') and g.current_user and hasattr(g.current_user, 'id'):
        user_id = str(g.current_user.id)

    total_pages = data.get('total_pages')
    if total_pages:
        try:
            total_pages = int(total_pages)
        except (ValueError, TypeError):
            total_pages = None

    chapter_number = data.get('chapter_number')

    try:
        with get_db_session() as session:
            import uuid
            now = datetime.now(timezone.utc)

            # Find or create progress record
            existing = session.query(ReadingProgress).filter(
                and_(
                    ReadingProgress.user_id == user_id,
                    ReadingProgress.manga_id == full_manga_id,
                    ReadingProgress.chapter_id == str(chapter_id)
                )
            ).first()

            if existing:
                existing.is_completed = True
                existing.current_page = total_pages or existing.total_pages or existing.current_page
                existing.last_read_at = now
            else:
                progress = ReadingProgress(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    manga_id=full_manga_id,
                    source_id=source_id,
                    chapter_id=str(chapter_id),
                    chapter_number=str(chapter_number) if chapter_number else None,
                    current_page=total_pages or 1,
                    total_pages=total_pages,
                    is_completed=True,
                    last_read_at=now
                )
                session.add(progress)

            # Log to history
            _log_to_history(
                session,
                user_id=user_id,
                manga_id=full_manga_id,
                source_id=source_id,
                chapter_id=str(chapter_id),
                chapter_num=str(chapter_number) if chapter_number else None,
                manga_title=data.get('manga_title'),
                manga_cover=data.get('manga_cover'),
                chapter_title=data.get('chapter_title'),
                pages_read=total_pages or 0,
                total_pages=total_pages
            )

            return jsonify({'success': True})

    except Exception as e:
        log(f"Error marking chapter read: {e}")
        return jsonify({'error': 'Failed to mark chapter as read'}), 500


@progress_bp.route('/clear', methods=['POST'])
@login_required
@csrf_protect
def clear_progress():
    """
    Clear reading progress for a manga or all manga.

    Request body:
        {
            "manga_id": "source:manga_id"  # optional, if not provided clears all
        }

    Returns:
        {"success": true, "cleared": N}
    """
    data = request.get_json(silent=True) or {}
    manga_id = data.get('manga_id')

    user_id = str(g.current_user.id)

    try:
        with get_db_session() as session:
            query = session.query(ReadingProgress).filter(
                ReadingProgress.user_id == user_id
            )

            if manga_id:
                query = query.filter(ReadingProgress.manga_id == manga_id)

            count = query.delete(synchronize_session=False)

            log(f"Cleared {count} progress records for user {user_id}")
            return jsonify({'success': True, 'cleared': count})

    except Exception as e:
        log(f"Error clearing progress: {e}")
        return jsonify({'error': 'Failed to clear progress'}), 500

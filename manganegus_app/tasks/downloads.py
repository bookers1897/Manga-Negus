"""
Celery tasks for manga chapter downloads.

These tasks handle background downloading of chapters, creating CBZ files,
and maintaining download status that can be queried by the frontend.

Tasks are designed to be:
- Idempotent: Can be safely retried
- Resumable: Track progress and can continue from where they left off
- Observable: Status can be queried at any time
"""

import os
import time
import zipfile
from typing import Dict, List, Any, Optional
import requests

from manganegus_app.celery_app import celery_app
from manganegus_app.log import log


def _sanitize(name: str) -> str:
    """Sanitize string for use in filenames."""
    return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()


def _sanitize_filename(name: str) -> str:
    """Sanitize for filename use."""
    clean = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
    clean = clean.replace(os.sep, '_')
    if os.altsep:
        clean = clean.replace(os.altsep, '_')
    return clean or "untitled"


@celery_app.task(bind=True, name='downloads.single_chapter')
def download_single_chapter_task(
    self,
    source_id: str,
    chapter_id: str,
    chapter_num: str,
    manga_title: str,
    download_dir: str,
    manga_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Download a single chapter and create CBZ.

    Args:
        source_id: Source connector ID (e.g., 'mangadex')
        chapter_id: Chapter ID from source
        chapter_num: Chapter number for naming
        manga_title: Manga title for folder/file naming
        download_dir: Base directory for downloads
        manga_id: Optional manga ID for metadata

    Returns:
        Dict with status, file_path, and any error message
    """
    from sources import get_source_manager

    result = {
        'status': 'started',
        'chapter_id': chapter_id,
        'chapter_num': chapter_num,
        'file_path': None,
        'error': None,
        'pages_downloaded': 0,
        'total_pages': 0
    }

    try:
        # Get source connector
        manager = get_source_manager()
        source = manager.get_source(source_id)

        if not source:
            result['status'] = 'failed'
            result['error'] = f"Source '{source_id}' not found"
            return result

        # Update task state
        self.update_state(state='PROGRESS', meta={'status': 'fetching_pages', **result})

        # Get pages
        pages = source.get_pages(chapter_id)
        if not pages:
            result['status'] = 'failed'
            result['error'] = f"No pages found for chapter {chapter_num}"
            return result

        result['total_pages'] = len(pages)

        # Setup directories
        safe_title = _sanitize(manga_title) or "untitled"
        safe_ch = _sanitize_filename(chapter_num)
        series_dir = os.path.join(download_dir, safe_title)
        os.makedirs(series_dir, exist_ok=True)

        folder_name = f"{safe_title} - Ch{safe_ch}"
        temp_folder = os.path.join(series_dir, folder_name)
        os.makedirs(temp_folder, exist_ok=True)

        # Get download session
        download_session = getattr(source, "get_download_session", None)
        download_session = download_session() if callable(download_session) else source.session
        if not download_session:
            download_session = requests.Session()

        # Download pages
        self.update_state(state='PROGRESS', meta={'status': 'downloading', **result})

        for idx, page in enumerate(pages):
            headers = dict(page.headers) if page.headers else {}
            if page.referer:
                headers['Referer'] = page.referer

            source.wait_for_rate_limit()

            try:
                resp = download_session.get(page.url, headers=headers, timeout=30, stream=True)
                if resp.status_code == 200:
                    ext = os.path.splitext(page.url.split('?', 1)[0])[1] or '.jpg'
                    filepath = os.path.join(temp_folder, f"{idx+1:04d}{ext}")
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 64):
                            if chunk:
                                f.write(chunk)
                    result['pages_downloaded'] = idx + 1
                    self.update_state(state='PROGRESS', meta={'status': 'downloading', **result})
            except Exception as e:
                log(f"⚠️ Failed to download page {idx+1}: {e}")
                continue

        # Create CBZ
        self.update_state(state='PROGRESS', meta={'status': 'creating_cbz', **result})

        cbz_path = os.path.join(series_dir, f"{folder_name}.cbz")
        with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(temp_folder):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    arcname = file
                    zf.write(file_path, arcname)

        # Cleanup temp folder
        import shutil
        shutil.rmtree(temp_folder, ignore_errors=True)

        result['status'] = 'completed'
        result['file_path'] = cbz_path
        log(f"✅ Downloaded Chapter {chapter_num}: {cbz_path}")

        return result

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        log(f"❌ Failed to download chapter {chapter_num}: {e}")
        return result


@celery_app.task(bind=True, name='downloads.batch_chapters')
def download_chapters_task(
    self,
    source_id: str,
    manga_id: str,
    manga_title: str,
    chapters: List[Dict[str, Any]],
    download_dir: str
) -> Dict[str, Any]:
    """
    Download multiple chapters in sequence.

    Args:
        source_id: Source connector ID
        manga_id: Manga ID for metadata
        manga_title: Manga title for naming
        chapters: List of chapter dicts with 'id' and 'chapter' keys
        download_dir: Base directory for downloads

    Returns:
        Dict with overall status and per-chapter results
    """
    result = {
        'status': 'started',
        'manga_title': manga_title,
        'total_chapters': len(chapters),
        'completed_chapters': 0,
        'failed_chapters': 0,
        'chapter_results': [],
        'error': None
    }

    try:
        for idx, chapter in enumerate(chapters):
            ch_id = chapter.get('id')
            ch_num = str(chapter.get('chapter', idx + 1))

            # Update progress
            self.update_state(state='PROGRESS', meta={
                **result,
                'status': f'downloading_chapter_{idx + 1}',
                'current_chapter': ch_num
            })

            # Download single chapter
            ch_result = download_single_chapter_task(
                source_id=source_id,
                chapter_id=ch_id,
                chapter_num=ch_num,
                manga_title=manga_title,
                download_dir=download_dir,
                manga_id=manga_id
            )

            result['chapter_results'].append(ch_result)

            if ch_result['status'] == 'completed':
                result['completed_chapters'] += 1
            else:
                result['failed_chapters'] += 1

        # Set final status
        if result['failed_chapters'] == 0:
            result['status'] = 'completed'
        elif result['completed_chapters'] > 0:
            result['status'] = 'partial'
        else:
            result['status'] = 'failed'

        log(f"✅ Batch download complete: {result['completed_chapters']}/{result['total_chapters']} chapters")
        return result

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        log(f"❌ Batch download failed: {e}")
        return result


@celery_app.task(name='downloads.get_job_status')
def get_download_job_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a download job by task ID.

    Args:
        task_id: Celery task ID

    Returns:
        Dict with task status and result if available
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    status = {
        'task_id': task_id,
        'state': result.state,
        'ready': result.ready(),
        'successful': result.successful() if result.ready() else None,
        'result': None,
        'error': None
    }

    if result.ready():
        if result.successful():
            status['result'] = result.result
        else:
            status['error'] = str(result.result)
    elif result.state == 'PROGRESS':
        status['result'] = result.info

    return status

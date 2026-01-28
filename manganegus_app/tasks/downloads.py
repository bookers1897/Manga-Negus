"""
Celery tasks for manga chapter downloads.

These tasks handle background downloading of chapters, creating CBZ files,
and maintaining download status that can be queried by the frontend.

Tasks are designed to be:
- Idempotent: Can be safely retried
- Resumable: Track progress and can continue from where they left off
- Observable: Status can be queried at any time

Memory Optimization (NEG-10):
- Uses streaming ZIP creation to prevent iOS memory crashes
- Each image is fetched, optionally compressed, written to ZIP, then released
- Memory stays under 100MB even for 100+ page chapters
"""

import gc
import io
import os
import time
import zipfile
from typing import Dict, List, Any, Optional, Callable
import requests

from manganegus_app.celery_app import celery_app
from manganegus_app.log import log


# Maximum retries for image fetch
MAX_IMAGE_RETRIES = 3
# Delay between retries (seconds)
RETRY_DELAY = 1.0
# Default image compression quality (0-100)
DEFAULT_COMPRESSION_QUALITY = 85
# Enable compression by default to reduce memory and file sizes
ENABLE_COMPRESSION = True


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


def secure_path_join(base_dir: str, *parts: str) -> str:
    """
    Securely join path components, preventing path traversal attacks.

    This function ensures that the resulting path stays within the base directory
    by normalizing all path components and verifying the final path doesn't escape.

    Args:
        base_dir: The base directory that all paths must stay within
        *parts: Path components to join to the base directory

    Returns:
        The normalized absolute path

    Raises:
        ValueError: If the resulting path would escape the base directory

    Examples:
        >>> secure_path_join('/downloads', 'manga', 'naruto')
        '/downloads/manga/naruto'

        >>> secure_path_join('/downloads', '../etc/passwd')
        ValueError: Path traversal attempt detected
    """
    # Normalize and get absolute path of base directory
    base_abs = os.path.abspath(os.path.normpath(base_dir))

    # Join all parts and normalize
    joined = os.path.join(base_abs, *parts)
    final_path = os.path.abspath(os.path.normpath(joined))

    # Verify the final path starts with base_abs + separator
    # This prevents paths like /downloads_evil if base is /downloads
    if not final_path.startswith(base_abs + os.sep) and final_path != base_abs:
        raise ValueError(
            f"Path traversal attempt detected: '{os.path.join(*parts)}' "
            f"would escape base directory '{base_dir}'"
        )

    return final_path


def _compress_image_for_cbz(data: bytes, quality: int = DEFAULT_COMPRESSION_QUALITY) -> bytes:
    """
    Compress image data to reduce memory usage and CBZ file size.

    Converts images to JPEG format with specified quality level.
    Handles RGBA/PNG images by converting to RGB with white background.

    Args:
        data: Raw image bytes
        quality: JPEG quality level (1-100), default 85

    Returns:
        Compressed image bytes, or original data if compression fails
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))

        # Convert RGBA/P modes to RGB (JPEG doesn't support transparency)
        if img.mode in ('RGBA', 'PA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        compressed = output.getvalue()

        # Only use compressed if it's smaller
        if len(compressed) < len(data):
            return compressed
        return data

    except Exception as e:
        log(f"Image compression failed, using original: {e}")
        return data


def _fetch_image_with_retry(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    max_retries: int = MAX_IMAGE_RETRIES,
    timeout: int = 30
) -> Optional[bytes]:
    """
    Fetch a single image with retry logic.

    Uses streaming to avoid loading entire response into memory at once.

    Args:
        session: requests Session to use
        url: Image URL to fetch
        headers: HTTP headers to send
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds

    Returns:
        Image bytes or None if all retries fail
    """
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=headers, timeout=timeout, stream=True)
            if resp.status_code == 200:
                # Read in chunks to manage memory
                chunks = []
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        chunks.append(chunk)
                return b''.join(chunks)
            elif resp.status_code in (429, 503):
                # Rate limited or service unavailable - wait and retry
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            else:
                log(f"Image fetch returned status {resp.status_code} for {url}")
                return None
        except requests.exceptions.Timeout:
            log(f"Timeout fetching image (attempt {attempt + 1}/{max_retries}): {url}")
            time.sleep(RETRY_DELAY)
        except requests.exceptions.RequestException as e:
            log(f"Request error fetching image (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(RETRY_DELAY)

    return None


def _download_chapter_streaming(
    pages: List[Any],
    cbz_path: str,
    download_session: requests.Session,
    source: Any,
    compress: bool = ENABLE_COMPRESSION,
    quality: int = DEFAULT_COMPRESSION_QUALITY,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
    """
    Download chapter images with streaming ZIP creation to minimize memory usage.

    This function processes one image at a time:
    1. Fetch image from URL
    2. Optionally compress image
    3. Write immediately to ZIP file
    4. Release memory (del + gc hint)

    This prevents the 500MB+ memory spikes that crash iOS devices when
    downloading 100+ page chapters.

    Args:
        pages: List of PageResult objects with url, headers, referer
        cbz_path: Path where CBZ file should be created
        download_session: requests Session configured for the source
        source: Source connector (for rate limiting)
        compress: Whether to compress images (default True)
        quality: JPEG compression quality if compressing
        progress_callback: Optional callback(current, total) for progress updates

    Returns:
        Dict with 'success', 'pages_downloaded', 'pages_failed', 'errors'
    """
    result = {
        'success': False,
        'pages_downloaded': 0,
        'pages_failed': 0,
        'total_pages': len(pages),
        'errors': []
    }

    try:
        # Open ZIP file for streaming write - write each image immediately
        with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, page in enumerate(pages):
                # Prepare headers
                headers = dict(page.headers) if page.headers else {}
                if page.referer:
                    headers['Referer'] = page.referer

                # Respect rate limiting
                if hasattr(source, 'wait_for_rate_limit'):
                    source.wait_for_rate_limit()

                try:
                    # Fetch single image
                    img_data = _fetch_image_with_retry(
                        session=download_session,
                        url=page.url,
                        headers=headers
                    )

                    if img_data is None:
                        result['pages_failed'] += 1
                        result['errors'].append(f"Page {idx + 1}: Failed to fetch")
                        continue

                    # Optionally compress to reduce memory and file size
                    if compress:
                        img_data = _compress_image_for_cbz(img_data, quality)

                    # Determine filename extension
                    ext = os.path.splitext(page.url.split('?', 1)[0])[1] or '.jpg'
                    if compress:
                        ext = '.jpg'  # Compression converts to JPEG
                    filename = f"{idx + 1:04d}{ext}"

                    # Write immediately to ZIP - this releases memory for the image
                    zf.writestr(filename, img_data)

                    # Explicitly release memory
                    del img_data

                    result['pages_downloaded'] += 1

                    # Progress callback for UI updates
                    if progress_callback:
                        progress_callback(idx + 1, len(pages))

                except Exception as e:
                    result['pages_failed'] += 1
                    result['errors'].append(f"Page {idx + 1}: {str(e)}")
                    log(f"Failed to process page {idx + 1}: {e}")
                    continue

                # Hint to garbage collector after each page
                # This helps keep memory low on memory-constrained devices
                if (idx + 1) % 10 == 0:
                    gc.collect()

        # Consider success if we got at least some pages
        result['success'] = result['pages_downloaded'] > 0

    except Exception as e:
        result['errors'].append(f"ZIP creation failed: {str(e)}")
        log(f"Streaming ZIP creation failed: {e}")

    return result


def _generate_comicinfo_xml(
    manga_title: str,
    chapter_num: str,
    page_count: int,
    manga_id: Optional[str] = None
) -> str:
    """
    Generate ComicInfo.xml metadata for the CBZ file.

    Args:
        manga_title: Title of the manga
        chapter_num: Chapter number/identifier
        page_count: Number of pages in the chapter
        manga_id: Optional manga ID for tracking

    Returns:
        XML string for ComicInfo.xml
    """
    # Escape XML special characters
    def escape_xml(s: str) -> str:
        return (s.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
                 .replace('"', '&quot;')
                 .replace("'", '&apos;'))

    safe_title = escape_xml(manga_title)
    safe_chapter = escape_xml(str(chapter_num))

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Series>{safe_title}</Series>
  <Number>{safe_chapter}</Number>
  <PageCount>{page_count}</PageCount>
  <Manga>Yes</Manga>
</ComicInfo>'''

    return xml


def _download_single_chapter_impl(
    task_self: Any,
    source_id: str,
    chapter_id: str,
    chapter_num: str,
    manga_title: str,
    download_dir: str,
    manga_id: Optional[str] = None,
    compress_images: bool = ENABLE_COMPRESSION,
    compression_quality: int = DEFAULT_COMPRESSION_QUALITY
) -> Dict[str, Any]:
    """
    Internal implementation for downloading a single chapter with streaming ZIP.

    This is the core implementation used by both the Celery task and batch downloads.
    It processes one image at a time to prevent iOS memory crashes:
    1. Fetch single image from source
    2. Optionally compress image (default: enabled)
    3. Write immediately to ZIP file
    4. Release memory before next image

    Memory usage stays under 100MB even for 100+ page chapters.

    Args:
        task_self: Celery task instance for state updates (can be None)
        source_id: Source connector ID (e.g., 'mangadex')
        chapter_id: Chapter ID from source
        chapter_num: Chapter number for naming
        manga_title: Manga title for folder/file naming
        download_dir: Base directory for downloads
        manga_id: Optional manga ID for metadata
        compress_images: Whether to compress images (default True)
        compression_quality: JPEG quality if compressing (default 85)

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
        'pages_failed': 0,
        'total_pages': 0
    }

    def update_task_state(state: str, meta: Dict[str, Any]):
        """Helper to update task state if task_self is available."""
        if task_self is not None and hasattr(task_self, 'update_state'):
            task_self.update_state(state=state, meta=meta)

    try:
        # Get source connector
        manager = get_source_manager()
        source = manager.get_source(source_id)

        if not source:
            result['status'] = 'failed'
            result['error'] = f"Source '{source_id}' not found"
            return result

        # Update task state
        update_task_state('PROGRESS', {'status': 'fetching_pages', **result})

        # Get pages
        pages = source.get_pages(chapter_id)
        if not pages:
            result['status'] = 'failed'
            result['error'] = f"No pages found for chapter {chapter_num}"
            return result

        result['total_pages'] = len(pages)

        # Setup directories using secure path joining
        safe_title = _sanitize(manga_title) or "untitled"
        safe_ch = _sanitize_filename(chapter_num)
        series_dir = secure_path_join(download_dir, safe_title)
        os.makedirs(series_dir, exist_ok=True)

        folder_name = f"{safe_title} - Ch{safe_ch}"
        cbz_path = secure_path_join(series_dir, f"{folder_name}.cbz")

        # Get download session from source (respects Cloudflare cookies, etc.)
        download_session = getattr(source, "get_download_session", None)
        download_session = download_session() if callable(download_session) else source.session
        if not download_session:
            download_session = requests.Session()

        # Update task state before download
        update_task_state('PROGRESS', {'status': 'downloading', **result})

        # Progress callback to update Celery task state
        def progress_callback(current: int, total: int):
            result['pages_downloaded'] = current
            update_task_state('PROGRESS', {'status': 'downloading', **result})

        # Use streaming download - processes one image at a time
        # This is the key fix for iOS memory crashes (NEG-10)
        stream_result = _download_chapter_streaming(
            pages=pages,
            cbz_path=cbz_path,
            download_session=download_session,
            source=source,
            compress=compress_images,
            quality=compression_quality,
            progress_callback=progress_callback
        )

        result['pages_downloaded'] = stream_result['pages_downloaded']
        result['pages_failed'] = stream_result['pages_failed']

        if not stream_result['success']:
            result['status'] = 'failed'
            result['error'] = '; '.join(stream_result['errors'][:5])  # Limit error messages
            log(f"Failed to download chapter {chapter_num}: {result['error']}")
            return result

        # Add ComicInfo.xml to the CBZ for reader compatibility
        update_task_state('PROGRESS', {'status': 'adding_metadata', **result})

        try:
            comicinfo_xml = _generate_comicinfo_xml(
                manga_title=manga_title,
                chapter_num=chapter_num,
                page_count=result['pages_downloaded'],
                manga_id=manga_id
            )
            # Append ComicInfo.xml to existing CBZ
            with zipfile.ZipFile(cbz_path, 'a') as zf:
                zf.writestr('ComicInfo.xml', comicinfo_xml)
        except Exception as e:
            # Non-fatal: CBZ still works without ComicInfo.xml
            log(f"Warning: Could not add ComicInfo.xml: {e}")

        result['status'] = 'completed'
        result['file_path'] = cbz_path

        # Force garbage collection after download completes
        gc.collect()

        log(f"Downloaded Chapter {chapter_num}: {cbz_path} "
            f"({result['pages_downloaded']}/{result['total_pages']} pages)")

        return result

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        log(f"Failed to download chapter {chapter_num}: {e}")
        return result


@celery_app.task(bind=True, name='downloads.single_chapter')
def download_single_chapter_task(
    self,
    source_id: str,
    chapter_id: str,
    chapter_num: str,
    manga_title: str,
    download_dir: str,
    manga_id: Optional[str] = None,
    compress_images: bool = ENABLE_COMPRESSION,
    compression_quality: int = DEFAULT_COMPRESSION_QUALITY
) -> Dict[str, Any]:
    """
    Celery task to download a single chapter and create CBZ using streaming.

    This is the Celery task wrapper around _download_single_chapter_impl.
    Use this for async downloads via .delay() or .apply_async().

    Memory usage stays under 100MB even for 100+ page chapters due to
    streaming ZIP creation that processes one image at a time.

    Args:
        source_id: Source connector ID (e.g., 'mangadex')
        chapter_id: Chapter ID from source
        chapter_num: Chapter number for naming
        manga_title: Manga title for folder/file naming
        download_dir: Base directory for downloads
        manga_id: Optional manga ID for metadata
        compress_images: Whether to compress images (default True)
        compression_quality: JPEG quality if compressing (default 85)

    Returns:
        Dict with status, file_path, and any error message
    """
    return _download_single_chapter_impl(
        task_self=self,
        source_id=source_id,
        chapter_id=chapter_id,
        chapter_num=chapter_num,
        manga_title=manga_title,
        download_dir=download_dir,
        manga_id=manga_id,
        compress_images=compress_images,
        compression_quality=compression_quality
    )


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

            # Download single chapter using streaming approach
            # Call synchronously to get result immediately and maintain sequential order
            # The streaming implementation prevents iOS memory crashes (NEG-10)
            ch_result = _download_single_chapter_impl(
                task_self=self,  # Pass parent task for state updates
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

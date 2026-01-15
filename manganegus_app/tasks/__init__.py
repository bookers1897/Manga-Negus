"""
Celery tasks for MangaNegus background processing.

This module contains all Celery tasks for:
- Chapter downloads
- Batch operations
- Scheduled updates

Usage:
    from manganegus_app.tasks import download_chapters_task

    # Submit task (returns AsyncResult)
    result = download_chapters_task.delay(
        source_id='mangadex',
        manga_id='abc-123',
        chapters=[{'id': 'ch-1', 'chapter': '1'}]
    )

    # Check status
    if result.ready():
        print(result.result)
"""

from manganegus_app.celery_app import is_celery_available

# Only import tasks if Celery is available
if is_celery_available():
    from .downloads import download_chapters_task, download_single_chapter_task
else:
    # Provide stubs when Celery isn't available
    download_chapters_task = None
    download_single_chapter_task = None

__all__ = ['download_chapters_task', 'download_single_chapter_task', 'is_celery_available']

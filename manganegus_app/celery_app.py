"""
Celery Application Configuration for MangaNegus.

This module provides background job processing using Celery with Redis as the broker.
It's OPTIONAL - if Redis isn't available, the app falls back to threading-based processing.

Setup:
1. Install Redis server: `sudo pacman -S redis` (Arch) or `apt install redis-server` (Debian)
2. Start Redis: `redis-server` or `systemctl start redis`
3. Set environment variable: `CELERY_BROKER_URL=redis://localhost:6379/0`
4. Start Celery worker: `celery -A manganegus_app.celery_app worker --loglevel=info`

Usage:
    from manganegus_app.celery_app import celery_app, is_celery_available

    if is_celery_available():
        result = download_chapter_task.delay(source_id, chapter_id)
        # result.id gives you the task ID to check status
    else:
        # Fall back to synchronous/threading processing
        download_chapter_sync(source_id, chapter_id)
"""

import os
from typing import Optional

# Try to import Celery - it's optional
try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None

# Redis connection URL from environment (defaults to localhost)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Flag to track if Celery is actually usable (not just importable)
_celery_tested = False
_celery_working = False


def _test_redis_connection() -> bool:
    """Test if Redis is actually reachable."""
    try:
        import redis
        client = redis.from_url(CELERY_BROKER_URL)
        client.ping()
        return True
    except Exception:
        return False


def is_celery_available() -> bool:
    """
    Check if Celery is available AND Redis is reachable.
    Results are cached after first check.
    """
    global _celery_tested, _celery_working

    if _celery_tested:
        return _celery_working

    _celery_tested = True

    if not CELERY_AVAILABLE:
        _celery_working = False
        return False

    # Check if CELERY_ENABLED is explicitly set to false
    if os.environ.get('CELERY_ENABLED', '').lower() in ('false', '0', 'no'):
        _celery_working = False
        return False

    # Test actual Redis connection
    _celery_working = _test_redis_connection()
    return _celery_working


# Create Celery app instance (only if Celery is importable)
celery_app: Optional[Celery] = None

if CELERY_AVAILABLE:
    celery_app = Celery(
        'manganegus',
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=['manganegus_app.tasks.downloads']
    )

    # Celery configuration
    celery_app.conf.update(
        # Task settings
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,

        # Task execution settings
        task_acks_late=True,  # Acknowledge after task completes (safer)
        task_reject_on_worker_lost=True,  # Requeue if worker dies
        task_time_limit=3600,  # 1 hour max per task
        task_soft_time_limit=3300,  # Soft limit at 55 minutes

        # Worker settings
        worker_prefetch_multiplier=1,  # Process one task at a time (for memory)
        worker_concurrency=2,  # 2 concurrent workers per process

        # Result backend settings
        result_expires=86400,  # Results expire after 24 hours

        # Retry settings
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=3,
    )


def get_celery_app() -> Optional[Celery]:
    """Get the Celery app instance, or None if unavailable."""
    if is_celery_available():
        return celery_app
    return None


# Convenience function for Flask integration
def init_celery_with_flask(app):
    """
    Initialize Celery with Flask application context.
    Call this in your Flask app factory if using Celery.
    """
    if celery_app is None:
        return None

    class FlaskTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = FlaskTask
    return celery_app

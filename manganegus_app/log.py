import os
import sys
import time
import queue
import json
import logging
from logging.handlers import RotatingFileHandler

try:
    from flask import g  # type: ignore
except Exception:  # pragma: no cover
    g = None

# Thread-safe message queue for real-time logging
msg_queue: queue.Queue = queue.Queue()

# Configure logging
logger = logging.getLogger("manganegus")
logger.setLevel(logging.INFO)

# Determine log file path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'manganegus.log')

# File Handler
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Stream Handler (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('%(message)s'))  # Keep stdout clean
logger.addHandler(stream_handler)

# Debug logging (local-only file)
DEBUG_LOGGING = os.environ.get('DEBUG_LOGGING', 'true').lower() in ('1', 'true', 'yes', 'on')
DEBUG_LOG_DIR = os.path.join(BASE_DIR, 'debugging')
os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
DEBUG_LOG_FILE = os.path.join(DEBUG_LOG_DIR, 'debug.log')

debug_logger = logging.getLogger("manganegus.debug")
debug_logger.setLevel(logging.INFO)
debug_logger.propagate = False
if not any(getattr(h, "baseFilename", None) == DEBUG_LOG_FILE for h in debug_logger.handlers):
    debug_handler = RotatingFileHandler(DEBUG_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=10)
    debug_handler.setFormatter(logging.Formatter('%(message)s'))
    debug_logger.addHandler(debug_handler)
if not DEBUG_LOGGING:
    debug_logger.disabled = True


def _request_prefix() -> str:
    """Return request id prefix if available."""
    try:
        if g and getattr(g, "request_id", None):
            return f"[{g.request_id}] "
    except RuntimeError:
        # Outside request context
        pass
    return ""


def log(msg: str) -> None:
    """Log a message to console, file, and message queue."""
    prefix = _request_prefix()
    full = f"{prefix}{msg}"
    
    # Log to file and stdout
    logger.info(full)
    
    # Add to queue for frontend
    timestamp = time.strftime("[%H:%M:%S]")
    msg_queue.put(f"{timestamp} {full}")


def debug_log_event(event: dict) -> None:
    """Write structured debug events to a local file."""
    if debug_logger.disabled:
        return
    try:
        debug_logger.info(json.dumps(event, ensure_ascii=True, separators=(',', ':')))
    except Exception as exc:
        logger.info(f"⚠️ Debug log failure: {exc}")

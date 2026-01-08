import time
import queue

try:
    from flask import g  # type: ignore
except Exception:  # pragma: no cover
    g = None

# Thread-safe message queue for real-time logging
msg_queue: queue.Queue = queue.Queue()


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
    """Log a message to console and message queue."""
    prefix = _request_prefix()
    full = f"{prefix}{msg}"
    print(full)
    timestamp = time.strftime("[%H:%M:%S]")
    msg_queue.put(f"{timestamp} {full}")

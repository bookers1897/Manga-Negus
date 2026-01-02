import time
import queue

# Thread-safe message queue for real-time logging
msg_queue: queue.Queue = queue.Queue()

def log(msg: str) -> None:
    """Log a message to console and message queue."""
    print(msg)
    timestamp = time.strftime("[%H:%M:%S]")
    msg_queue.put(f"{timestamp} {msg}")

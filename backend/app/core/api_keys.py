import hashlib
import secrets
import threading
import time
from collections import deque
from typing import Deque, Dict

KEY_PREFIX = "fk_"

def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)

def hash_api_key(key: str) -> str:
    # Keys are 256 bits of randomness, so a plain SHA-256 is enough (no need for a slow password hash).
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

class RateLimiter:
    """In-memory sliding-window limiter, per key id. Per-process: use a shared store if the API is scaled out."""
    def __init__(self):
        self._hits: Dict[int, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key_id: int, limit_per_minute: int) -> float:
        """Returns 0 if the call is allowed, otherwise the seconds to wait before retrying."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key_id, deque())
            while hits and now - hits[0] >= 60.0:
                hits.popleft()
            if len(hits) >= limit_per_minute:
                return 60.0 - (now - hits[0])
            hits.append(now)
            return 0.0

    def reset(self):
        with self._lock:
            self._hits.clear()

rate_limiter = RateLimiter()

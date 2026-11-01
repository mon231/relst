import time
import threading
from collections import deque
from typing import List, Optional


MAX_STORED_BODY = 64 * 1024


class TraceLog:
    """Thread-safe ring-buffer of the latest handled requests"""

    def __init__(self, limit: int = 500):
        self.__lock = threading.Lock()
        self.__entries = deque(maxlen=limit)
        self.__next_id = 1

    def record(self, **fields) -> dict:
        with self.__lock:
            entry = {'id': self.__next_id, 'time': time.time(), **fields}
            self.__next_id += 1
            self.__entries.append(entry)

        return entry

    def entries(self, after: int = 0, limit: Optional[int] = None) -> List[dict]:
        with self.__lock:
            matching = [entry for entry in self.__entries if entry['id'] > after]

        return matching if limit is None else matching[-limit:]

    def clear(self):
        with self.__lock:
            self.__entries.clear()


def render_body(body: bytes, is_binary: bool) -> dict:
    shown = body[:MAX_STORED_BODY]

    return {
        'text': shown.hex() if is_binary else shown.decode('utf-8', errors='replace'),
        'size': len(body),
        'truncated': len(body) > MAX_STORED_BODY,
    }

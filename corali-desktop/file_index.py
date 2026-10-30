"""In-memory incremental index; periodic reconciliation catches external edits."""

import heapq
import threading
import time


class FileIndex:
    def __init__(self, app, interval=5):
        self.app = app
        self.interval = interval
        self.entries = {}
        self.last_scan = None
        self.lock = threading.RLock()

    def snapshot(self, refresh=False):
        with self.lock:
            if (
                refresh
                or self.last_scan is None
                or time.monotonic() - self.last_scan >= self.interval
            ):
                self.entries = {row["id"]: row for row in self.app.scan_entries()}
                self.last_scan = time.monotonic()
            rows = heapq.nlargest(
                5000, self.entries.values(), key=lambda r: (r["_mtime"], r["id"])
            )
            return [{k: v for k, v in row.items() if k != "_mtime"} for row in rows]

    def update(self, folder):
        with self.lock:
            prefix = folder.relative_to(self.app.root).as_posix() + "/"
            self.entries = {
                key: value
                for key, value in self.entries.items()
                if not key.startswith(prefix)
            }
            for row in self.app.scan_entries(folder):
                self.entries[row["id"]] = row

    def invalidate(self):
        with self.lock:
            self.last_scan = None

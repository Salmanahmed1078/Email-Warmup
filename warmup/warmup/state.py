"""JSON state file with an exclusive lock so overlapping cron runs cannot double-send."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

EMPTY = {"days": {}, "actions": [], "handled": {}, "bounces": [], "seen_bounces": {},
         "paused": {}, "alert": None, "problems": {}}


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        self._lock = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = open(self.path.with_suffix(".lock"), "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another warm-up run is in progress; exiting") from None
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        for k, v in EMPTY.items():
            self.data.setdefault(k, json.loads(json.dumps(v)))
        return self

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        os.replace(tmp, self.path)

    def __exit__(self, *exc):
        self.save()
        fcntl.flock(self._lock, fcntl.LOCK_UN)
        self._lock.close()

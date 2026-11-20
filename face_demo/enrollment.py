"""Bounded, expiring camera enrollment drafts; capture state lives on the server."""

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Draft:
    name: str
    email: str
    consent_at: str
    expires_at: float
    streak: int = 0
    last_frame: float = 0
    last_box: dict | None = None
    sample: Any = None
    completed_user: dict | None = None
    busy: bool = False


class Enrollments:
    def __init__(self, required_matches=3):
        self.items = {}
        self.lock = threading.Lock()
        self.required_matches = required_matches

    def purge(self):
        with self.lock:
            now = time.monotonic()
            self.items = {token: item for token, item in self.items.items() if item.expires_at > now or item.busy}

    def create(self, name, email):
        self.purge()
        with self.lock:
            if len(self.items) >= 50:
                raise ValueError("Terlalu banyak sesi pendaftaran. Coba lagi beberapa menit lagi.")
            token = secrets.token_urlsafe(32)
            self.items[token] = Draft(name, email, datetime.now(timezone.utc).isoformat(), time.monotonic() + 300)
            return token

    def get(self, token):
        with self.lock:
            item = self.items.get(token)
            if item is None or item.expires_at <= time.monotonic():
                if item is not None and not item.busy:
                    self.items.pop(token, None)
                raise KeyError("Sesi pendaftaran berakhir. Mulai kamera kembali.")
            return item

    def begin(self, token, *, frame=False):
        item = self.get(token)
        with self.lock:
            if self.items.get(token) is not item:
                raise KeyError("Sesi pendaftaran sudah dibatalkan.")
            now = time.monotonic()
            if item.busy or (frame and now - item.last_frame < .4):
                raise ValueError("Pemeriksaan terlalu cepat. Tunggu sesaat.")
            if frame:
                if now - item.last_frame > 2.5:
                    item.streak = 0
                    item.last_box = None
                item.last_frame = now
            item.busy = True
            return item

    def observe(self, item, result):
        with self.lock:
            if not result["ready"]:
                item.streak = 0
                item.last_box = None
                return False
            box = result["face"]
            if item.last_box:
                previous = item.last_box
                # Normalize against face size so stability is resolution independent.
                motion = max(abs(box[key] - previous[key]) / max(previous["w"], 1) for key in ("x", "y", "w", "h"))
                if motion > .12:
                    item.streak = 0
            item.last_box = box.copy()
            item.streak = min(self.required_matches, item.streak + 1)
            return item.streak >= self.required_matches

    def finish(self, item):
        with self.lock:
            item.busy = False

    def remove(self, token):
        with self.lock:
            self.items.pop(token, None)

    def remove_user(self, user_id):
        with self.lock:
            self.items = {token: item for token, item in self.items.items()
                          if not item.completed_user or item.completed_user["id"] != user_id}

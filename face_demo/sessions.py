"""Short-lived, identity-bound verification state, maintained by the server."""

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass
class Session:
    user_id: str
    expires_at: float
    streak: int = 0
    last_frame: float = 0
    busy: bool = False


class Sessions:
    def __init__(self, required_matches=3):
        self.required_matches = required_matches
        self.items = {}
        self.lock = threading.Lock()

    def create(self, user_id):
        now = time.monotonic()
        with self.lock:
            self.items = {key: item for key, item in self.items.items() if item.expires_at > now}
            if len(self.items) >= 200:
                raise ValueError("Terlalu banyak sesi aktif. Tunggu beberapa menit.")
            token = secrets.token_urlsafe(32)
            self.items[token] = Session(user_id, now + 180)
        return token

    def begin(self, token):
        with self.lock:
            item = self.items.get(token)
            now = time.monotonic()
            if item is None or item.expires_at <= now:
                self.items.pop(token, None)
                raise KeyError("Sesi berakhir. Mulai verifikasi kembali.")
            if item.busy or now - item.last_frame < 0.6:
                raise ValueError("Pemeriksaan terlalu cepat. Tunggu sesaat.")
            if now - item.last_frame > 10:
                item.streak = 0
            item.busy = True
            item.last_frame = now
            return item

    def finish(self, item, matched):
        with self.lock:
            item.busy = False
            item.streak = min(self.required_matches, item.streak + 1) if matched else 0
            return item.streak

    def remove_user(self, user_id):
        with self.lock:
            self.items = {key: item for key, item in self.items.items() if item.user_id != user_id}

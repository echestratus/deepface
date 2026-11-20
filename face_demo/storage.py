"""Local SQLite storage; never expose embeddings through the API."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np

from .engine import PIPELINE, Sample


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                consent_at TEXT NOT NULL, pipeline TEXT NOT NULL,
                embedding BLOB NOT NULL, photo BLOB NOT NULL
            )""")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def list_users(self):
        with self.connection() as db:
            rows = db.execute("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get(self, user_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def email_exists(self, email):
        with self.connection() as db:
            return db.execute("SELECT 1 FROM users WHERE email = ?", (email.lower(),)).fetchone() is not None

    def create(self, name: str, email: str, sample: Sample, consent_at=None):
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as db:
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                user_id, name, email.lower(), now, consent_at or now, PIPELINE,
                sample.embedding.astype(np.float32).tobytes(), sample.photo,
            ))
        return {"id": user_id, "name": name, "email": email.lower(), "created_at": now}

    def delete(self, user_id):
        with self.connection() as db:
            changed = db.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount
        # Checkpoint after committing the deletion as well.
        with self.connection() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return bool(changed)

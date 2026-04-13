"""
SQLite-backed storage for torium-mcp multi-tenant state.

DB path: ~/.config/torium/mcp.db

Tables:
  allowlist          — email addresses permitted to use the remote server
  tori_sessions      — per-user Tori.fi refresh tokens (one row per tori user_id)
  mcp_clients        — OAuth DCR client registrations (persisted across restarts)
  mcp_refresh_tokens — MCP-level refresh tokens, linked to tori_sessions
  mcp_access_tokens  — MCP-level access tokens, linked to tori_sessions
"""

import json
import os
import secrets
import sqlite3
import threading
import time
from typing import Optional

DB_PATH = os.path.expanduser("~/.config/torium/mcp.db")

_CREATE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS allowlist (
    email      TEXT PRIMARY KEY,
    added_at   INTEGER NOT NULL,
    note       TEXT
);

CREATE TABLE IF NOT EXISTS tori_sessions (
    user_id             INTEGER PRIMARY KEY,
    email               TEXT NOT NULL,
    tori_refresh_token  TEXT NOT NULL,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tori_sessions_email ON tori_sessions(email);

CREATE TABLE IF NOT EXISTS mcp_clients (
    client_id        TEXT PRIMARY KEY,
    client_info_json TEXT NOT NULL,
    created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mcp_refresh_tokens (
    refresh_token TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES tori_sessions(user_id) ON DELETE CASCADE,
    client_id     TEXT NOT NULL,
    scopes_json   TEXT NOT NULL,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS mcp_refresh_user ON mcp_refresh_tokens(user_id);

CREATE TABLE IF NOT EXISTS mcp_access_tokens (
    access_token TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES tori_sessions(user_id) ON DELETE CASCADE,
    client_id    TEXT NOT NULL,
    scopes_json  TEXT NOT NULL,
    expires_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS mcp_access_user ON mcp_access_tokens(user_id);

CREATE TABLE IF NOT EXISTS deletion_tokens (
    token      TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at REAL NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS temp_images (
    image_id      TEXT PRIMARY KEY,
    upload_token  TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    mime_type     TEXT NOT NULL,
    created_at    REAL NOT NULL,
    uploaded      INTEGER DEFAULT 0,
    used          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS temp_images_token ON temp_images(upload_token);
"""


class Storage:
    """Thread-safe SQLite wrapper for torium-mcp multi-tenant state."""

    def __init__(self, path: str = DB_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        # executescript commits automatically; sets WAL + foreign_keys for this connection
        self._conn.executescript(_CREATE_SCHEMA)

    @classmethod
    def open(cls, path: str = DB_PATH) -> "Storage":
        return cls(path)

    # ── Allowlist ──────────────────────────────────────────────────────────────

    def is_allowed(self, email: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM allowlist WHERE email=?", (email,)
        ).fetchone()
        return row is not None

    def allow_email(self, email: str, note: Optional[str] = None) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO allowlist (email, added_at, note) VALUES (?,?,?)",
                    (email, int(time.time()), note),
                )

    def revoke_email(self, email: str) -> Optional[int]:
        """Remove email from allowlist and cascade-delete their sessions. Returns user_id or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id FROM tori_sessions WHERE email=?", (email,)
            ).fetchone()
            user_id = row["user_id"] if row else None
            self._conn.execute("PRAGMA foreign_keys=ON")
            with self._conn:
                self._conn.execute("DELETE FROM tori_sessions WHERE email=?", (email,))
                self._conn.execute("DELETE FROM allowlist WHERE email=?", (email,))
        return user_id

    def list_allowed(self) -> list:
        return self._conn.execute(
            "SELECT email, added_at, note FROM allowlist ORDER BY added_at"
        ).fetchall()

    # ── Tori sessions ─────────────────────────────────────────────────────────

    def upsert_tori_session(self, user_id: int, email: str, refresh_token: str) -> None:
        now = int(time.time())
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """INSERT INTO tori_sessions (user_id, email, tori_refresh_token, created_at, updated_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           email=excluded.email,
                           tori_refresh_token=excluded.tori_refresh_token,
                           updated_at=excluded.updated_at""",
                    (user_id, email, refresh_token, now, now),
                )

    def get_tori_session(self, user_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT user_id, email, tori_refresh_token FROM tori_sessions WHERE user_id=?",
            (user_id,),
        ).fetchone()

    def update_tori_refresh(self, user_id: int, new_refresh_token: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "UPDATE tori_sessions SET tori_refresh_token=?, updated_at=? WHERE user_id=?",
                    (new_refresh_token, int(time.time()), user_id),
                )

    # ── MCP clients (DCR) ─────────────────────────────────────────────────────

    def get_client_json(self, client_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT client_info_json FROM mcp_clients WHERE client_id=?", (client_id,)
        ).fetchone()
        return row["client_info_json"] if row else None

    def put_client(self, client_id: str, client_info_json: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mcp_clients (client_id, client_info_json, created_at) VALUES (?,?,?)",
                    (client_id, client_info_json, int(time.time())),
                )

    # ── MCP refresh tokens ────────────────────────────────────────────────────

    def put_mcp_refresh(self, token: str, user_id: int, client_id: str, scopes: list) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mcp_refresh_tokens "
                    "(refresh_token, user_id, client_id, scopes_json, created_at) VALUES (?,?,?,?,?)",
                    (token, user_id, client_id, json.dumps(scopes), int(time.time())),
                )

    def get_mcp_refresh(self, token: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT user_id, client_id, scopes_json FROM mcp_refresh_tokens WHERE refresh_token=?",
            (token,),
        ).fetchone()

    def pop_mcp_refresh(self, token: str) -> Optional[sqlite3.Row]:
        """Atomically read and delete (refresh tokens are single-use)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, client_id, scopes_json FROM mcp_refresh_tokens WHERE refresh_token=?",
                (token,),
            ).fetchone()
            if row:
                with self._conn:
                    self._conn.execute(
                        "DELETE FROM mcp_refresh_tokens WHERE refresh_token=?", (token,)
                    )
        return row

    # ── MCP access tokens ─────────────────────────────────────────────────────

    def put_mcp_access(
        self, token: str, user_id: int, client_id: str, scopes: list, expires_at: int
    ) -> None:
        now = int(time.time())
        with self._lock:
            with self._conn:
                # Piggyback cleanup of expired tokens to avoid a separate vacuum job
                self._conn.execute(
                    "DELETE FROM mcp_access_tokens WHERE expires_at<?", (now,)
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO mcp_access_tokens "
                    "(access_token, user_id, client_id, scopes_json, expires_at) VALUES (?,?,?,?,?)",
                    (token, user_id, client_id, json.dumps(scopes), expires_at),
                )

    def get_mcp_access(self, token: str) -> Optional[sqlite3.Row]:
        now = int(time.time())
        return self._conn.execute(
            "SELECT user_id, client_id, scopes_json, expires_at FROM mcp_access_tokens "
            "WHERE access_token=? AND expires_at>?",
            (token, now),
        ).fetchone()

    def delete_mcp_access(self, token: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM mcp_access_tokens WHERE access_token=?", (token,)
                )

    # ── Deletion tokens ────────────────────────────────────────────────────────

    def email_has_data(self, email: str) -> bool:
        """Check if any session data exists for this email."""
        row = self._conn.execute(
            "SELECT 1 FROM tori_sessions WHERE email=?", (email,)
        ).fetchone()
        return row is not None

    def create_deletion_token(self, email: str) -> str:
        """Create a 24-hour single-use deletion token for the given email."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO deletion_tokens (token, email, created_at, used) VALUES (?,?,?,0)",
                    (token, email, time.time()),
                )
        return token

    def consume_deletion_token(self, token: str) -> Optional[str]:
        """Return email if token is valid, unused, and <24h old. Marks it used. Returns None if invalid."""
        cutoff = time.time() - 86400
        with self._lock:
            row = self._conn.execute(
                "SELECT email, created_at, used FROM deletion_tokens WHERE token=?",
                (token,),
            ).fetchone()
            if row is None or row["used"] or row["created_at"] < cutoff:
                return None
            with self._conn:
                self._conn.execute(
                    "UPDATE deletion_tokens SET used=1 WHERE token=?", (token,)
                )
        return row["email"]

    # ── Temp images (presigned upload) ────────────────────────────────────────

    def register_temp_image(self, image_id: str, upload_token: str, user_id: str, file_path: str, mime: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO temp_images (image_id, upload_token, user_id, file_path, mime_type, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (image_id, upload_token, user_id, file_path, mime, time.time()),
                )

    def get_temp_image_by_token(self, upload_token: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT image_id, user_id, file_path, created_at, uploaded, used "
            "FROM temp_images WHERE upload_token=?",
            (upload_token,),
        ).fetchone()
        return dict(row) if row else None

    def mark_temp_image_uploaded(self, image_id: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("UPDATE temp_images SET uploaded=1 WHERE image_id=?", (image_id,))

    def consume_temp_image(self, image_id: str, user_id: str) -> bytes:
        row = self._conn.execute(
            "SELECT file_path FROM temp_images WHERE image_id=? AND user_id=? AND uploaded=1 AND used=0",
            (image_id, user_id),
        ).fetchone()
        if not row:
            raise ValueError(f"image_id {image_id!r} not found, not uploaded yet, or already used")
        with open(row["file_path"], "rb") as f:
            data = f.read()
        with self._lock:
            with self._conn:
                self._conn.execute("UPDATE temp_images SET used=1 WHERE image_id=?", (image_id,))
        return data

    def cleanup_old_temp_images(self, max_age_seconds: int = 3600) -> None:
        cutoff = time.time() - max_age_seconds
        rows = self._conn.execute(
            "SELECT file_path FROM temp_images WHERE created_at < ? OR used=1", (cutoff,)
        ).fetchall()
        for row in rows:
            try:
                os.unlink(row["file_path"])
            except FileNotFoundError:
                pass
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM temp_images WHERE created_at < ? OR used=1", (cutoff,))

    # ── User data deletion ─────────────────────────────────────────────────────

    def delete_user_data(self, email: str) -> bool:
        """Delete all session and token data for a user by email. Returns True if any rows deleted."""
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id FROM tori_sessions WHERE email=?", (email,)
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("PRAGMA foreign_keys=ON")
            with self._conn:
                # CASCADE deletes mcp_refresh_tokens and mcp_access_tokens via FK
                self._conn.execute("DELETE FROM tori_sessions WHERE email=?", (email,))
                self._conn.execute("DELETE FROM allowlist WHERE email=?", (email,))
        return True

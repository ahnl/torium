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

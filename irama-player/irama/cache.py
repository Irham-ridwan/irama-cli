"""Local SQLite Caching for Irama Nusantara album metadata."""

import os
import sys
import json
import time
import sqlite3
from typing import Optional, Dict, Any
from contextlib import contextmanager

DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def get_default_cache_dir() -> str:
    """Returns platform-specific user cache directory."""
    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "irama")
    else:
        base = os.getenv("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        return os.path.join(base, "irama")


def get_default_cache_db_path() -> str:
    """Returns platform-specific SQLite cache database path."""
    return os.getenv("IRAMA_CACHE_DB", os.path.join(get_default_cache_dir(), "cache.db"))


class AlbumCache:
    """SQLite-backed cache for album metadata with TTL support and graceful degradation."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self.db_path = db_path or get_default_cache_db_path()
        self.ttl_seconds = ttl_seconds
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager that ensures SQLite connections are properly closed on exit."""
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initializes database schema safely."""
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS album_cache (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        artist TEXT,
                        year TEXT,
                        payload_json TEXT,
                        updated_at REAL
                    )
                    """
                )
                conn.commit()
        except (sqlite3.Error, OSError):
            # Graceful degradation if database cannot be initialized
            pass

    def get(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw album payload from cache if present and not expired."""
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT payload_json, updated_at FROM album_cache WHERE id = ?",
                    (str(album_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                payload_json = row["payload_json"]
                updated_at = row["updated_at"]

                # Check TTL expiration
                if self.ttl_seconds > 0 and (time.time() - updated_at) > self.ttl_seconds:
                    return None

                return json.loads(payload_json)
        except (sqlite3.Error, json.JSONDecodeError, OSError):
            # Graceful degradation: treat errors as cache miss
            return None

    def set(
        self,
        album_id: str,
        title: str,
        artist: str,
        year: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Upserts album payload into cache."""
        try:
            payload_json = json.dumps(payload)
            now = time.time()
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO album_cache (id, title, artist, year, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        year=excluded.year,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (str(album_id), str(title), str(artist), str(year), payload_json, now),
                )
                conn.commit()
                return True
        except (sqlite3.Error, TypeError, OSError):
            return False

    def delete(self, album_id: str) -> bool:
        """Deletes specific album from cache."""
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM album_cache WHERE id = ?", (str(album_id),))
                conn.commit()
                return True
        except (sqlite3.Error, OSError):
            return False

    def clear(self) -> bool:
        """Clears all records from cache."""
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM album_cache")
                conn.commit()
                return True
        except (sqlite3.Error, OSError):
            return False

    def is_cached(self, album_id: str) -> bool:
        """Checks if valid (unexpired) cache entry exists for album_id."""
        return self.get(album_id) is not None

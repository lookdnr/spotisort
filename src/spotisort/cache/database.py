"""SQLite connection and schema management for the cache.

:class:`Database` owns the connection and the full schema (the cache tables are
small and closely related, so keeping their DDL and the version check in one
place keeps migrations simple). It deals only in storage; converting domain
models to/from the stored payloads is the job of the individual cache classes.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)

__all__ = ["SCHEMA_VERSION", "Database"]

#: Bump when the stored format changes; a mismatch rebuilds the cache tables.
SCHEMA_VERSION = 1

_META_KEY_SCHEMA_VERSION = "schema_version"


class Database:
    """A thin wrapper over a SQLite connection with versioned schema setup.

    The connection is opened lazily on first use and reused for the process.

    Args:
        path: Filesystem path to the SQLite database file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """The live connection, opening and initialising it on first access."""
        if self._connection is None:
            self._connection = self._connect()
        return self._connection

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        self._initialise(connection)
        logger.debug("Opened cache database at %s.", self._path)
        return connection

    def _initialise(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = connection.execute(
            "SELECT value FROM meta WHERE key = ?", (_META_KEY_SCHEMA_VERSION,)
        ).fetchone()
        current_version = int(row["value"]) if row is not None else None

        if current_version is not None and current_version != SCHEMA_VERSION:
            logger.info(
                "Cache schema changed (%s -> %s); rebuilding cache tables.",
                current_version,
                SCHEMA_VERSION,
            )
            connection.execute("DROP TABLE IF EXISTS saved_tracks")
            connection.execute("DROP TABLE IF EXISTS artist_genres")

        connection.execute(
            "CREATE TABLE IF NOT EXISTS saved_tracks ("
            "position INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS artist_genres ("
            "artist_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (_META_KEY_SCHEMA_VERSION, str(SCHEMA_VERSION)),
        )
        connection.commit()

    def get_meta(self, key: str) -> str | None:
        """Return a stored metadata value, or ``None`` if unset."""
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        """Store a metadata value, replacing any existing entry."""
        self.connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
        self.connection.commit()

    def close(self) -> None:
        """Close the connection if it is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> Database:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

"""Persistent cache of the user's liked songs."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from spotisort.cache.database import Database
from spotisort.cache.serialization import decode_saved_track, encode_saved_track
from spotisort.models import SavedTrack

logger = logging.getLogger(__name__)

__all__ = ["LibraryCache"]

_META_SYNCED_AT = "library_synced_at"


class LibraryCache:
    """Stores and retrieves the full list of saved tracks.

    A successful :meth:`save` records a "synced at" timestamp; :meth:`load`
    returns ``None`` until then (a cache miss), distinct from an empty list (a
    library with no liked songs). :meth:`is_fresh` applies the configured TTL.

    Args:
        database: The cache database.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, tracks: Sequence[SavedTrack]) -> None:
        """Replace the cached liked songs and stamp the sync time (now, UTC)."""
        connection = self._db.connection
        connection.execute("DELETE FROM saved_tracks")
        connection.executemany(
            "INSERT INTO saved_tracks (position, payload) VALUES (?, ?)",
            (
                (position, json.dumps(encode_saved_track(track)))
                for position, track in enumerate(tracks)
            ),
        )
        connection.commit()
        self._db.set_meta(_META_SYNCED_AT, datetime.now(UTC).isoformat())
        logger.debug("Cached %d saved track(s).", len(tracks))

    def load(self) -> list[SavedTrack] | None:
        """Return the cached saved tracks, or ``None`` if never synced."""
        if self.synced_at() is None:
            return None
        rows = self._db.connection.execute(
            "SELECT payload FROM saved_tracks ORDER BY position"
        ).fetchall()
        return [decode_saved_track(json.loads(row["payload"])) for row in rows]

    def clear(self) -> None:
        """Drop the cached liked songs and the sync timestamp (forces a miss)."""
        connection = self._db.connection
        connection.execute("DELETE FROM saved_tracks")
        connection.execute("DELETE FROM meta WHERE key = ?", (_META_SYNCED_AT,))
        connection.commit()
        logger.debug("Cleared cached saved tracks.")

    def synced_at(self) -> datetime | None:
        """When the library was last cached (UTC), or ``None`` if never."""
        raw = self._db.get_meta(_META_SYNCED_AT)
        return datetime.fromisoformat(raw) if raw else None

    def is_fresh(self, ttl: timedelta | None) -> bool:
        """Whether a cached copy exists and is within ``ttl`` (``None`` = no expiry)."""
        synced = self.synced_at()
        if synced is None:
            return False
        if ttl is None:
            return True
        return datetime.now(UTC) - synced < ttl

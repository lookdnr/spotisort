"""Persistent cache of artist genres.

Genres are effectively static, so this cache has no TTL: an artist stays cached
until the whole cache is cleared. Storing artists by id lets the cached artist
repository fetch only the ids it is missing.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence

from spotisort.cache.database import Database
from spotisort.cache.serialization import decode_artist, encode_artist
from spotisort.models import Artist

logger = logging.getLogger(__name__)

__all__ = ["ArtistGenreCache"]

#: Keep IN-clause sizes well under SQLite's bound-parameter limit.
_QUERY_CHUNK = 500


class ArtistGenreCache:
    """Stores and retrieves artists (with their genres) by id.

    Args:
        database: The cache database.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_many(self, artist_ids: Sequence[str]) -> dict[str, Artist]:
        """Return cached artists for the given ids (absent ids are omitted)."""
        unique = [artist_id for artist_id in dict.fromkeys(artist_ids) if artist_id]
        result: dict[str, Artist] = {}
        for start in range(0, len(unique), _QUERY_CHUNK):
            chunk = unique[start : start + _QUERY_CHUNK]
            placeholders = ", ".join("?" * len(chunk))
            rows = self._db.connection.execute(
                f"SELECT artist_id, payload FROM artist_genres WHERE artist_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                result[row["artist_id"]] = decode_artist(json.loads(row["payload"]))
        return result

    def put_many(self, artists: Iterable[Artist]) -> None:
        """Store the given artists, replacing any existing entries."""
        rows = [
            (artist.id, json.dumps(encode_artist(artist))) for artist in artists if artist.id
        ]
        if not rows:
            return
        self._db.connection.executemany(
            "INSERT OR REPLACE INTO artist_genres (artist_id, payload) VALUES (?, ?)", rows
        )
        self._db.connection.commit()
        logger.debug("Cached %d artist(s).", len(rows))

    def clear(self) -> None:
        """Drop all cached artists."""
        self._db.connection.execute("DELETE FROM artist_genres")
        self._db.connection.commit()
        logger.debug("Cleared cached artists.")

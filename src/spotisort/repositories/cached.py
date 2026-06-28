"""Caching repositories that sit in front of the live ones.

Each wraps a live repository (the delegate) and a SQLite-backed cache, and
implements the same Protocol the services depend on. They add persistence
without the services knowing anything has changed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import timedelta

from spotisort.cache.artist_cache import ArtistGenreCache
from spotisort.cache.library_cache import LibraryCache
from spotisort.models import Artist, SavedTrack
from spotisort.repositories.protocols import ArtistSource, SavedTrackRepository

logger = logging.getLogger(__name__)

__all__ = ["CachedArtistRepository", "CachedLikedSongsRepository"]


class CachedLikedSongsRepository:
    """A :class:`SavedTrackRepository` backed by a persistent cache.

    Reads come from the cache while it is fresh; otherwise the delegate is
    queried and the result cached. Writes go straight to the delegate and then
    invalidate the cache, since the library has changed. ``contains`` always hits
    the delegate so verification reflects the live library.

    Args:
        delegate: The live repository to fall back to.
        cache: The persistent liked-songs cache.
        ttl: How long cached data stays fresh; ``None`` means it never expires.
    """

    def __init__(
        self,
        delegate: SavedTrackRepository,
        cache: LibraryCache,
        *,
        ttl: timedelta | None,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._ttl = ttl

    def list_all(self) -> list[SavedTrack]:
        if self._cache.is_fresh(self._ttl):
            cached = self._cache.load()
            if cached is not None:
                logger.info("Loaded %d liked song(s) from cache.", len(cached))
                return cached
        tracks = self._delegate.list_all()
        self._cache.save(tracks)
        return tracks

    def refresh(self) -> list[SavedTrack]:
        """Force a re-sync from the live API, replacing the cache."""
        self._cache.clear()
        return self.list_all()

    def add(self, track_ids: Sequence[str]) -> int:
        count = self._delegate.add(track_ids)
        if count:
            self._cache.clear()
        return count

    def remove(self, track_ids: Sequence[str]) -> int:
        count = self._delegate.remove(track_ids)
        if count:
            self._cache.clear()
        return count

    def contains(self, track_ids: Sequence[str]) -> dict[str, bool]:
        return self._delegate.contains(track_ids)


class CachedArtistRepository:
    """An :class:`ArtistSource` that caches artist genres persistently.

    Args:
        delegate: The live artist source to fetch cache misses from.
        cache: The persistent artist-genre cache.
    """

    def __init__(self, delegate: ArtistSource, cache: ArtistGenreCache) -> None:
        self._delegate = delegate
        self._cache = cache

    def get_many(self, artist_ids: Sequence[str]) -> dict[str, Artist]:
        unique = [artist_id for artist_id in dict.fromkeys(artist_ids) if artist_id]
        result = self._cache.get_many(unique)
        missing = [artist_id for artist_id in unique if artist_id not in result]
        if missing:
            fetched = self._delegate.get_many(missing)
            if fetched:
                self._cache.put_many(fetched.values())
            result.update(fetched)
            logger.debug("Fetched %d artist(s) not in cache.", len(fetched))
        return result

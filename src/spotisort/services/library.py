"""The :class:`SpotifyLibrary` service — the user's liked songs."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timezone

from spotisort.models import SavedTrack, Track
from spotisort.repositories import LikedSongsRepository

logger = logging.getLogger(__name__)

__all__ = ["SpotifyLibrary"]

#: Anything that can identify a track for like/unlike operations.
TrackLike = Track | SavedTrack | str


class SpotifyLibrary:
    """Represents the user's liked songs.

    The library lazily loads all saved tracks on first access and caches them
    until :meth:`refresh` is called (or a mutation invalidates the cache). All
    filter methods operate in memory over that cache, so they are cheap to chain
    and do not hit the network.

    This service is where match semantics for the library live; the models and
    repositories deliberately stay free of search logic.

    Args:
        repository: The data source for saved tracks.
    """

    def __init__(self, repository: LikedSongsRepository) -> None:
        self._repository = repository
        self._cache: list[SavedTrack] | None = None

    # ------------------------------------------------------------------ #
    # Cache management
    # ------------------------------------------------------------------ #

    def refresh(self) -> list[SavedTrack]:
        """Reload all saved tracks from Spotify, replacing the cache.

        Returns:
            A copy of the freshly loaded saved tracks.
        """
        self._cache = self._repository.list_all()
        logger.info("Library refreshed: %d saved track(s).", len(self._cache))
        return list(self._cache)

    def all_tracks(self) -> list[SavedTrack]:
        """Return all saved tracks, loading them on first use.

        Returns:
            A copy of the cached saved tracks (mutating it will not affect the
            library's cache).
        """
        return list(self._ensure_loaded())

    @property
    def is_loaded(self) -> bool:
        """Whether the saved tracks have been loaded into the cache."""
        return self._cache is not None

    def invalidate(self) -> None:
        """Drop the cache so the next access reloads from Spotify."""
        self._cache = None

    def _ensure_loaded(self) -> list[SavedTrack]:
        """Return the cache, loading it from the repository if necessary."""
        if self._cache is None:
            self._cache = self._repository.list_all()
            logger.debug("Library loaded: %d saved track(s).", len(self._cache))
        return self._cache

    # ------------------------------------------------------------------ #
    # Filters (operate in memory over the cache)
    # ------------------------------------------------------------------ #

    def before(self, moment: date | datetime) -> list[SavedTrack]:
        """Saved tracks added strictly before ``moment``.

        Args:
            moment: A date or datetime. A naive value (or a plain date, taken as
                midnight) is interpreted as UTC, matching Spotify's timestamps.
        """
        boundary = _coerce_utc(moment)
        return [saved for saved in self._ensure_loaded() if saved.added_at < boundary]

    def after(self, moment: date | datetime) -> list[SavedTrack]:
        """Saved tracks added strictly after ``moment`` (see :meth:`before`)."""
        boundary = _coerce_utc(moment)
        return [saved for saved in self._ensure_loaded() if saved.added_at > boundary]

    def by_artist(self, name: str) -> list[SavedTrack]:
        """Saved tracks that credit an artist whose name matches ``name``.

        Matching is case-insensitive and exact (after trimming). Use
        :meth:`search` for partial matches.
        """
        target = _normalize(name)
        return [
            saved
            for saved in self._ensure_loaded()
            if any(_normalize(artist) == target for artist in saved.track.artist_names)
        ]

    def by_album(self, name: str) -> list[SavedTrack]:
        """Saved tracks whose album name matches ``name`` (case-insensitive, exact)."""
        target = _normalize(name)
        return [
            saved
            for saved in self._ensure_loaded()
            if saved.track.album is not None and _normalize(saved.track.album.name) == target
        ]

    def by_year(self, year: int) -> list[SavedTrack]:
        """Saved tracks whose album was released in ``year``."""
        return [saved for saved in self._ensure_loaded() if saved.track.release_year == year]

    def search(self, query: str) -> list[SavedTrack]:
        """Saved tracks matching ``query`` across title, artists and album.

        Matching is a case-insensitive substring test. An empty or whitespace
        query matches nothing.
        """
        target = _normalize(query)
        if not target:
            return []
        return [saved for saved in self._ensure_loaded() if target in _haystack(saved.track)]

    # ------------------------------------------------------------------ #
    # Membership / mutation
    # ------------------------------------------------------------------ #

    def contains(self, tracks: Iterable[TrackLike]) -> dict[str, bool]:
        """Check, per track id, whether each track is currently liked.

        Reads straight from Spotify (not the cache), so it reflects the live
        library state — useful for verifying mutations.
        """
        return self._repository.contains(_extract_ids(tracks))

    def is_liked(self, track: TrackLike) -> bool:
        """Whether a single track is currently liked."""
        ids = _extract_ids([track])
        if not ids:
            return False
        return self.contains(ids).get(ids[0], False)

    def like(self, tracks: Iterable[TrackLike]) -> int:
        """Add the given tracks to the library and invalidate the cache.

        Returns:
            The number of tracks submitted.
        """
        ids = _extract_ids(tracks)
        count = self._repository.add(ids)
        if count:
            self.invalidate()
        return count

    def unlike(self, tracks: Iterable[TrackLike]) -> int:
        """Remove the given tracks from the library and invalidate the cache.

        Returns:
            The number of tracks submitted.
        """
        ids = _extract_ids(tracks)
        count = self._repository.remove(ids)
        if count:
            self.invalidate()
        return count


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _normalize(value: str) -> str:
    """Normalise a string for case-insensitive comparison."""
    return value.strip().casefold()


def _haystack(track: Track) -> str:
    """Build a normalised, searchable blob from a track's text fields."""
    parts = [track.name, *track.artist_names]
    if track.album is not None:
        parts.append(track.album.name)
    return _normalize(" ".join(parts))


def _coerce_utc(moment: date | datetime) -> datetime:
    """Coerce a date/datetime into a timezone-aware UTC datetime."""
    # datetime is a subclass of date, so check it first.
    if isinstance(moment, datetime):
        dt = moment
    elif isinstance(moment, date):
        dt = datetime(moment.year, moment.month, moment.day)
    else:  # pragma: no cover - guarded by type hints
        raise TypeError(f"Expected a date or datetime, got {type(moment).__name__}.")
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _extract_ids(tracks: Iterable[TrackLike]) -> list[str]:
    """Extract non-empty track ids from tracks, saved tracks or raw id strings."""
    ids: list[str] = []
    for item in tracks:
        if isinstance(item, str):
            track_id = item
        elif isinstance(item, SavedTrack):
            track_id = item.track.id
        elif isinstance(item, Track):
            track_id = item.id
        else:  # pragma: no cover - guarded by type hints
            raise TypeError(f"Cannot derive a track id from {type(item).__name__}.")
        if track_id:
            ids.append(track_id)
        else:
            logger.warning("Skipping a track with no id (likely a local file).")
    return ids

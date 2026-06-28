"""The :class:`Playlist` domain model."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from spotisort.models.track import Track

__all__ = ["Playlist"]


@dataclass(frozen=True, slots=True)
class Playlist:
    """A Spotify playlist.

    A playlist may be carrying its items or not. When fetched as part of a
    listing only its metadata is populated and :attr:`tracks` is ``None``; the
    repository loads the items separately. Distinguishing "not loaded" (``None``)
    from "loaded and empty" (``()``) matters, so :attr:`tracks` is deliberately
    nullable rather than defaulting to an empty tuple.

    Attributes:
        id: The Spotify playlist id.
        name: The playlist name.
        owner_id: The owning user's id, if known.
        owner_name: The owning user's display name, if known.
        description: The playlist description, if any.
        public: Whether the playlist is public. ``None`` when unknown.
        collaborative: Whether the playlist is collaborative.
        snapshot_id: Spotify's snapshot id for the playlist's current state.
        total_tracks: Total number of items reported by Spotify, if known.
        uri: The Spotify URI, if known.
        url: The public Spotify web URL, if known.
        tracks: The loaded tracks, or ``None`` if items have not been loaded.
    """

    id: str
    name: str
    owner_id: str | None = None
    owner_name: str | None = None
    description: str | None = None
    public: bool | None = None
    collaborative: bool = False
    snapshot_id: str | None = None
    total_tracks: int | None = None
    uri: str | None = None
    url: str | None = None
    tracks: tuple[Track, ...] | None = None

    @property
    def is_loaded(self) -> bool:
        """Whether the playlist's items have been loaded into :attr:`tracks`."""
        return self.tracks is not None

    @property
    def track_count(self) -> int:
        """Number of tracks: the loaded count if available, else the reported total."""
        if self.tracks is not None:
            return len(self.tracks)
        return self.total_tracks or 0

    def with_tracks(self, tracks: Iterable[Track]) -> Playlist:
        """Return a copy of this playlist with its items set to ``tracks``."""
        return replace(self, tracks=tuple(tracks))

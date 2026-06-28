"""Repository interfaces consumed by the service layer.

Services depend on these Protocols rather than concrete repository classes, so
alternative implementations — notably the SQLite-backed caching repositories —
can be substituted without changing any business logic. The live repositories
satisfy these structurally; no inheritance is required.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from spotisort.models import Artist, SavedTrack

__all__ = ["ArtistSource", "SavedTrackRepository"]


class SavedTrackRepository(Protocol):
    """The liked-songs operations the library service depends on."""

    def list_all(self) -> list[SavedTrack]: ...

    def add(self, track_ids: Sequence[str]) -> int: ...

    def remove(self, track_ids: Sequence[str]) -> int: ...

    def contains(self, track_ids: Sequence[str]) -> dict[str, bool]: ...


class ArtistSource(Protocol):
    """The artist lookup the genre classifier depends on."""

    def get_many(self, artist_ids: Sequence[str]) -> dict[str, Artist]: ...

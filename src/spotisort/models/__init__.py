"""Domain models.

Pure, immutable dataclasses representing Spotify entities. They contain no
knowledge of the Spotify API or its JSON shape — conversion from raw payloads is
handled by :mod:`spotisort.mapping`. This keeps the models reusable across any
backing store (live API, SQLite cache, fixtures) without modification.
"""

from __future__ import annotations

from spotisort.models.album import Album
from spotisort.models.artist import Artist
from spotisort.models.playlist import Playlist
from spotisort.models.track import SavedTrack, Track

__all__ = ["Artist", "Album", "Track", "SavedTrack", "Playlist"]

"""Repository layer.

Repositories turn the client's raw, single-request API into model-returning,
bulk operations: they follow pagination cursors on reads and split writes into
API-sized batches. They contain no business policy — that lives in
:mod:`spotisort.services`.
"""

from __future__ import annotations

from spotisort.repositories.artists import ArtistRepository
from spotisort.repositories.base import Repository
from spotisort.repositories.cached import CachedArtistRepository, CachedLikedSongsRepository
from spotisort.repositories.liked_songs import LikedSongsRepository
from spotisort.repositories.playlists import PlaylistRepository
from spotisort.repositories.protocols import ArtistSource, SavedTrackRepository

__all__ = [
    "ArtistRepository",
    "ArtistSource",
    "CachedArtistRepository",
    "CachedLikedSongsRepository",
    "LikedSongsRepository",
    "PlaylistRepository",
    "Repository",
    "SavedTrackRepository",
]

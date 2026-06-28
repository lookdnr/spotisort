"""Repository layer.

Repositories turn the client's raw, single-request API into model-returning,
bulk operations: they follow pagination cursors on reads and split writes into
API-sized batches. They contain no business policy — that lives in
:mod:`spotisort.services`.
"""

from __future__ import annotations

from spotisort.repositories.base import Repository
from spotisort.repositories.liked_songs import LikedSongsRepository
from spotisort.repositories.playlists import PlaylistRepository

__all__ = ["Repository", "LikedSongsRepository", "PlaylistRepository"]

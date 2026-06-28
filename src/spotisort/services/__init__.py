"""Service layer: business logic.

Services orchestrate repositories and apply the application's rules — caching,
filtering, and multi-step operations. They depend on repositories and domain
models, never on the API client or raw payloads directly, which keeps them
unit-testable with in-memory fakes.
"""

from __future__ import annotations

from spotisort.services.library import SpotifyLibrary
from spotisort.services.operations import (
    LibraryOrganiser,
    MoveResult,
    MoveVerificationError,
)
from spotisort.services.playlists import PlaylistManager

__all__ = [
    "SpotifyLibrary",
    "PlaylistManager",
    "LibraryOrganiser",
    "MoveResult",
    "MoveVerificationError",
]

"""The thin Spotify communication layer.

This package is the only place in spotisort that imports Spotipy or handles raw
API payloads. Everything above it works with domain models instead.

The exception types are re-exported here for convenience so callers can write
``from spotisort.api import RateLimitError`` without reaching into submodules.
"""

from __future__ import annotations

from spotisort.api.exceptions import (
    AuthenticationError,
    MappingError,
    PlaylistNotFoundError,
    RateLimitError,
    RequestFailedError,
    ResourceNotFoundError,
    RetriesExhaustedError,
    SpotifyApiError,
    SpotisortError,
    TrackNotFoundError,
)

__all__ = [
    "AuthenticationError",
    "MappingError",
    "PlaylistNotFoundError",
    "RateLimitError",
    "RequestFailedError",
    "ResourceNotFoundError",
    "RetriesExhaustedError",
    "SpotifyApiError",
    "SpotisortError",
    "TrackNotFoundError",
]

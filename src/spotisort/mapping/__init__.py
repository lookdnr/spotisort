"""Mapping layer: raw Spotify payloads -> domain models.

The mappers here are the only code (besides :mod:`spotisort.api`) that is aware
of Spotify's JSON shape. Everything above this layer works with domain models.
"""

from __future__ import annotations

from spotisort.mapping.mappers import (
    AlbumMapper,
    ArtistMapper,
    PlaylistMapper,
    SavedTrackMapper,
    SpotifyMapper,
    TrackMapper,
)

__all__ = [
    "AlbumMapper",
    "ArtistMapper",
    "PlaylistMapper",
    "SavedTrackMapper",
    "SpotifyMapper",
    "TrackMapper",
]

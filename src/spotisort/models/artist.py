"""The :class:`Artist` domain model."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Artist"]


@dataclass(frozen=True, slots=True)
class Artist:
    """A Spotify artist.

    Only the fields spotisort currently needs are modelled. The dataclass is
    immutable and hashable so artists can be used in sets and as dict keys.

    Attributes:
        id: The Spotify artist id. May be empty for artists embedded in local
            tracks, which Spotify does not assign ids to.
        name: The artist's display name.
        uri: The Spotify URI (e.g. ``spotify:artist:...``), if known.
        url: The public Spotify web URL, if known.
        genres: The artist's genres. Only populated when the artist was loaded
            as a full object (``GET /v1/artists``); the artists embedded in track
            payloads do not include genres, so this is empty for them.
    """

    id: str
    name: str
    uri: str | None = None
    url: str | None = None
    genres: tuple[str, ...] = ()

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
    """

    id: str
    name: str
    uri: str | None = None
    url: str | None = None

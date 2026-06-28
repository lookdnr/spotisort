"""The :class:`Album` domain model."""

from __future__ import annotations

from dataclasses import dataclass

from spotisort.models.artist import Artist

__all__ = ["Album"]


@dataclass(frozen=True, slots=True)
class Album:
    """A Spotify album.

    Attributes:
        id: The Spotify album id.
        name: The album title.
        artists: The album's artists, in order.
        release_date: The raw release date string from Spotify. Its precision
            varies (``"1981"``, ``"1981-12"`` or ``"1981-12-25"``); see
            :attr:`release_date_precision`.
        release_date_precision: ``"year"``, ``"month"`` or ``"day"``.
        total_tracks: Number of tracks on the album, if known.
        uri: The Spotify URI, if known.
        url: The public Spotify web URL, if known.
    """

    id: str
    name: str
    artists: tuple[Artist, ...] = ()
    release_date: str | None = None
    release_date_precision: str | None = None
    total_tracks: int | None = None
    uri: str | None = None
    url: str | None = None

    @property
    def release_year(self) -> int | None:
        """The four-digit release year, or ``None`` if it cannot be determined.

        Works regardless of :attr:`release_date_precision`, since Spotify always
        prefixes the date with the year.
        """
        if not self.release_date:
            return None
        head = self.release_date[:4]
        return int(head) if head.isdigit() else None

    @property
    def artist_names(self) -> tuple[str, ...]:
        """The names of the album's artists, in order."""
        return tuple(artist.name for artist in self.artists)

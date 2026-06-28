"""The :class:`Track` model and the :class:`SavedTrack` library wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from spotisort.models.album import Album
from spotisort.models.artist import Artist

__all__ = ["SavedTrack", "Track"]


@dataclass(frozen=True, slots=True)
class Track:
    """A Spotify track.

    Attributes:
        id: The Spotify track id. May be empty for local files.
        name: The track title.
        artists: The track's artists, in order.
        album: The album the track belongs to, if known.
        duration_ms: Track length in milliseconds.
        explicit: Whether the track is flagged explicit.
        disc_number: The disc the track appears on, if known.
        track_number: The track's position on its disc, if known.
        popularity: Spotify's 0-100 popularity score, if known.
        is_local: Whether this is a local file rather than a catalogue track.
        uri: The Spotify URI (``spotify:track:...`` or a local URI). This is the
            identifier used when adding/removing the track to/from playlists.
        url: The public Spotify web URL, if known.
    """

    id: str
    name: str
    artists: tuple[Artist, ...] = ()
    album: Album | None = None
    duration_ms: int = 0
    explicit: bool = False
    disc_number: int | None = None
    track_number: int | None = None
    popularity: int | None = None
    is_local: bool = False
    uri: str | None = None
    url: str | None = None

    @property
    def primary_artist(self) -> Artist | None:
        """The first credited artist, or ``None`` if there are none."""
        return self.artists[0] if self.artists else None

    @property
    def artist_names(self) -> tuple[str, ...]:
        """The names of the track's artists, in order."""
        return tuple(artist.name for artist in self.artists)

    @property
    def release_year(self) -> int | None:
        """The track's album release year, if an album and date are known."""
        return self.album.release_year if self.album else None

    @property
    def duration(self) -> timedelta:
        """The track length as a :class:`~datetime.timedelta`."""
        return timedelta(milliseconds=self.duration_ms)

    def display_name(self) -> str:
        """A human-readable ``"Artist 1, Artist 2 - Title"`` label."""
        artists = ", ".join(self.artist_names)
        return f"{artists} - {self.name}" if artists else self.name


@dataclass(frozen=True, slots=True)
class SavedTrack:
    """A track saved in the user's library ("liked song").

    Wraps a :class:`Track` together with the moment it was added to the library.
    ``added_at`` belongs to the *save relationship*, not to the track itself,
    which is why it lives here rather than on :class:`Track` — and it is what
    :meth:`SpotifyLibrary.before`/``after`` filter on.

    Attributes:
        track: The saved track.
        added_at: When the track was added to the library. Timezone-aware (UTC).
    """

    track: Track
    added_at: datetime

    @property
    def added_year(self) -> int:
        """The calendar year in which the track was added to the library."""
        return self.added_at.year

    @property
    def id(self) -> str:
        """Convenience accessor for the underlying track id."""
        return self.track.id

    @property
    def uri(self) -> str | None:
        """Convenience accessor for the underlying track URI."""
        return self.track.uri

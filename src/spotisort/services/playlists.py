"""The :class:`PlaylistManager` service — managing playlists."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from spotisort.models import Playlist, SavedTrack, Track
from spotisort.repositories import PlaylistRepository

logger = logging.getLogger(__name__)

__all__ = ["PlaylistManager"]

#: A playlist argument: either a loaded :class:`Playlist` or its id.
PlaylistRef = Playlist | str

#: A track argument for membership operations: a track, saved track, or a raw
#: string (a Spotify URI, or a bare track id which is expanded to a track URI).
TrackRef = Track | SavedTrack | str


class PlaylistManager:
    """Creates, finds and edits playlists.

    Wraps :class:`PlaylistRepository`, adding the conveniences callers expect —
    name-based lookup and :meth:`get_or_create` — on top of the repository's
    id-based, batched primitives.

    Args:
        repository: The playlist data source.
    """

    def __init__(self, repository: PlaylistRepository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def all_playlists(self) -> list[Playlist]:
        """Return metadata for every playlist the user owns or follows."""
        return self._repository.list_all()

    def get(self, playlist: PlaylistRef, *, with_tracks: bool = False) -> Playlist:
        """Fetch a playlist by id (or refresh a given :class:`Playlist`).

        Args:
            playlist: A playlist id or an existing :class:`Playlist`.
            with_tracks: When ``True``, load and attach all of its tracks.

        Raises:
            PlaylistNotFoundError: If no playlist with that id exists.
        """
        playlist_id = _ref_id(playlist)
        if with_tracks:
            return self._repository.get_with_tracks(playlist_id)
        return self._repository.get(playlist_id)

    def find_by_name(self, name: str) -> Playlist | None:
        """Find the first playlist whose name matches ``name``.

        Matching is case-insensitive and exact (after trimming). If several
        playlists share the name, the first is returned and a warning is logged.
        """
        target = _normalize(name)
        matches = [pl for pl in self.all_playlists() if _normalize(pl.name) == target]
        if not matches:
            return None
        if len(matches) > 1:
            logger.warning("Found %d playlists named %r; using the first.", len(matches), name)
        return matches[0]

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def create(
        self,
        name: str,
        *,
        public: bool = False,
        collaborative: bool = False,
        description: str | None = None,
    ) -> Playlist:
        """Create a new playlist. Spotify permits duplicate names."""
        return self._repository.create(
            name,
            public=public,
            collaborative=collaborative,
            description=description,
        )

    def get_or_create(
        self,
        name: str,
        *,
        public: bool = False,
        collaborative: bool = False,
        description: str | None = None,
    ) -> Playlist:
        """Return the existing playlist named ``name``, or create it if absent.

        The creation arguments are only applied when a new playlist is created;
        an existing match is returned unchanged.
        """
        existing = self.find_by_name(name)
        if existing is not None:
            logger.debug("Reusing existing playlist %r (%s).", existing.name, existing.id)
            return existing
        return self.create(
            name,
            public=public,
            collaborative=collaborative,
            description=description,
        )

    def rename(self, playlist: PlaylistRef, new_name: str) -> Playlist:
        """Rename a playlist and return its refreshed metadata."""
        playlist_id = _ref_id(playlist)
        self._repository.change_details(playlist_id, name=new_name)
        logger.info("Renamed playlist %s to %r.", playlist_id, new_name)
        return self._repository.get(playlist_id)

    def delete(self, playlist: PlaylistRef) -> None:
        """Delete (unfollow) a playlist."""
        self._repository.unfollow(_ref_id(playlist))

    # ------------------------------------------------------------------ #
    # Track membership
    # ------------------------------------------------------------------ #

    def add_tracks(self, playlist: PlaylistRef, tracks: Iterable[TrackRef]) -> int:
        """Append tracks to a playlist. Returns the number submitted."""
        return self._repository.add_tracks(_ref_id(playlist), _extract_uris(tracks))

    def remove_tracks(self, playlist: PlaylistRef, tracks: Iterable[TrackRef]) -> int:
        """Remove all occurrences of the given tracks. Returns the number submitted."""
        return self._repository.remove_tracks(_ref_id(playlist), _extract_uris(tracks))

    def replace_tracks(self, playlist: PlaylistRef, tracks: Iterable[TrackRef]) -> int:
        """Replace a playlist's contents with ``tracks`` (empty clears it).

        Returns the number of tracks the playlist now contains.
        """
        return self._repository.replace_tracks(_ref_id(playlist), _extract_uris(tracks))


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _normalize(value: str) -> str:
    """Normalise a string for case-insensitive comparison."""
    return value.strip().casefold()


def _ref_id(playlist: PlaylistRef) -> str:
    """Resolve a playlist id from a :class:`Playlist` or an id string."""
    return playlist.id if isinstance(playlist, Playlist) else playlist


def _extract_uris(tracks: Iterable[TrackRef]) -> list[str]:
    """Resolve track URIs from tracks, saved tracks, URIs or bare ids.

    A raw string already containing a ``:`` is treated as a full URI; otherwise
    it is assumed to be a track id and expanded to ``spotify:track:<id>``.
    """
    uris: list[str] = []
    for item in tracks:
        uri = _track_uri(item)
        if uri:
            uris.append(uri)
        else:
            logger.warning("Skipping a track with no usable URI (likely a local file).")
    return uris


def _track_uri(item: TrackRef) -> str | None:
    """Resolve a single track reference to a Spotify URI, or ``None``."""
    if isinstance(item, str):
        return item if ":" in item else (f"spotify:track:{item}" if item else None)
    track = item.track if isinstance(item, SavedTrack) else item
    if track.uri:
        return track.uri
    return f"spotify:track:{track.id}" if track.id else None

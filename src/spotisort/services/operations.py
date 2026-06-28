"""Cross-cutting library/playlist operations: copy and move.

These operations span both the library and playlists, so they live in their own
coordinating service — :class:`LibraryOrganiser` — rather than on either
:class:`SpotifyLibrary` or :class:`PlaylistManager`. That keeps those two
services from depending on each other.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from spotisort.api.exceptions import SpotisortError
from spotisort.models import Playlist, SavedTrack
from spotisort.services.library import SpotifyLibrary
from spotisort.services.playlists import PlaylistManager, PlaylistRef, TrackRef

logger = logging.getLogger(__name__)

__all__ = ["LibraryOrganiser", "MoveResult", "MoveVerificationError"]


class MoveVerificationError(SpotisortError):
    """Raised when a move cannot confirm tracks reached the destination playlist.

    When this is raised, the tracks have **not** been removed from the library,
    so no songs are lost: the move is aborted after the (idempotent-ish) add step
    but before the destructive unlike step.

    Attributes:
        missing_count: How many tracks could not be confirmed present.
        playlist_id: The destination playlist id.
    """

    def __init__(self, missing_count: int, playlist_id: str) -> None:
        super().__init__(
            f"Could not verify {missing_count} track(s) reached playlist {playlist_id}; "
            "aborting before removing them from the library."
        )
        self.missing_count = missing_count
        self.playlist_id = playlist_id


@dataclass(frozen=True, slots=True)
class MoveResult:
    """The outcome of a successful move.

    Attributes:
        playlist: The destination playlist, reloaded with its tracks.
        added: Number of tracks submitted to the playlist.
        removed: Number of tracks removed from the library.
    """

    playlist: Playlist
    added: int
    removed: int


class LibraryOrganiser:
    """Coordinates the library and playlists for copy/move operations.

    Args:
        library: The liked-songs service.
        playlists: The playlist service.
    """

    def __init__(self, library: SpotifyLibrary, playlists: PlaylistManager) -> None:
        self._library = library
        self._playlists = playlists

    def copy_to_playlist(self, tracks: Iterable[TrackRef], playlist: PlaylistRef) -> int:
        """Add tracks to a playlist, leaving the library untouched.

        Returns:
            The number of tracks submitted to the playlist.
        """
        tracks = list(tracks)
        added = self._playlists.add_tracks(playlist, tracks)
        logger.info("Copied %d track(s) to playlist %s.", added, _ref_id(playlist))
        return added

    def move_to_playlist(self, tracks: Iterable[TrackRef], playlist: PlaylistRef) -> MoveResult:
        """Move tracks from the library into a playlist.

        The steps are deliberately ordered so that nothing is lost on failure:

        1. add the tracks to the playlist;
        2. reload the playlist and verify every track is present;
        3. only then remove the tracks from the library.

        Raises:
            MoveVerificationError: If step 2 cannot confirm the tracks landed, in
                which case the library is left unchanged.
        """
        tracks = list(tracks)
        playlist_id = _ref_id(playlist)

        added = self._playlists.add_tracks(playlist, tracks)

        refreshed = self._playlists.get(playlist_id, with_tracks=True)
        missing = _unverified(tracks, refreshed)
        if missing:
            logger.error(
                "Move aborted: %d of %d track(s) not found in playlist %s after add.",
                len(missing),
                len(tracks),
                playlist_id,
            )
            raise MoveVerificationError(len(missing), playlist_id)

        removed = self._library.unlike(_ids(tracks))
        logger.info(
            "Moved %d track(s) into playlist %s (removed %d from library).",
            added,
            playlist_id,
            removed,
        )
        return MoveResult(playlist=refreshed, added=added, removed=removed)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _ref_id(playlist: PlaylistRef) -> str:
    """Resolve a playlist id from a :class:`Playlist` or an id string."""
    return playlist.id if isinstance(playlist, Playlist) else playlist


def _resolve_identity(item: TrackRef) -> tuple[str | None, str | None]:
    """Return a ``(track_id, uri)`` pair for any kind of track reference."""
    if isinstance(item, str):
        if ":" in item:
            track_id = item.rsplit(":", 1)[-1] if item.startswith("spotify:track:") else None
            return (track_id or None), item
        return (item or None), (f"spotify:track:{item}" if item else None)
    track = item.track if isinstance(item, SavedTrack) else item
    track_id = track.id or None
    uri = track.uri or (f"spotify:track:{track_id}" if track_id else None)
    return track_id, uri


def _ids(tracks: Iterable[TrackRef]) -> list[str]:
    """Resolve the non-empty track ids needed to unlike tracks from the library."""
    return [track_id for track_id, _ in map(_resolve_identity, tracks) if track_id]


def _unverified(tracks: Iterable[TrackRef], playlist: Playlist) -> list[TrackRef]:
    """Return the references that are not present in ``playlist``'s loaded tracks."""
    present = playlist.tracks or ()
    present_ids = {track.id for track in present if track.id}
    present_uris = {track.uri for track in present if track.uri}

    missing: list[TrackRef] = []
    for item in tracks:
        track_id, uri = _resolve_identity(item)
        if (track_id and track_id in present_ids) or (uri and uri in present_uris):
            continue
        missing.append(item)
    return missing

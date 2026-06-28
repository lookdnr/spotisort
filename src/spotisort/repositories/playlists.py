"""Repository for playlists and their tracks."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from spotisort.api.exceptions import PlaylistNotFoundError, RequestFailedError
from spotisort.models import Playlist, Track
from spotisort.repositories.base import Repository

logger = logging.getLogger(__name__)

__all__ = ["PlaylistRepository"]


class PlaylistRepository(Repository):
    """Reads and modifies playlists.

    Reads follow pagination automatically; writes are batched against the
    configured limits. A ``404`` from Spotify for a given playlist id is
    translated into :class:`PlaylistNotFoundError` so callers get a meaningful,
    typed failure.
    """

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def list_all(self) -> list[Playlist]:
        """Fetch metadata for every playlist the user owns or follows.

        The returned playlists carry metadata only (``tracks is None``); use
        :meth:`load_tracks` or :meth:`get_with_tracks` to load their items.
        """
        page_size = self._limits.playlists_page
        items = self._iter_offset_items(
            lambda limit, offset: self._client.current_user_playlists(limit=limit, offset=offset),
            page_size=page_size,
        )
        playlists = [self._mapper.playlists.map(item) for item in items]
        logger.debug("Fetched %d playlist(s).", len(playlists))
        return playlists

    def get(self, playlist_id: str) -> Playlist:
        """Fetch a single playlist's metadata (without loading its items)."""
        with self._translate_not_found(playlist_id):
            payload = self._client.playlist(playlist_id)
        return self._mapper.playlists.map(payload)

    def load_tracks(self, playlist_id: str) -> tuple[Track, ...]:
        """Fetch all of a playlist's tracks, following pagination automatically.

        Unavailable items (whose track Spotify reports as ``null``) are skipped.
        """
        page_size = self._limits.playlist_items_page
        with self._translate_not_found(playlist_id):
            items = self._iter_offset_items(
                lambda limit, offset: self._client.playlist_items(
                    playlist_id, limit=limit, offset=offset
                ),
                page_size=page_size,
            )
            tracks = self._mapper.playlists.map_items(items)
        logger.debug("Loaded %d track(s) from playlist %s.", len(tracks), playlist_id)
        return tracks

    def get_with_tracks(self, playlist_id: str) -> Playlist:
        """Fetch a playlist's metadata and attach all of its loaded tracks."""
        playlist = self.get(playlist_id)
        return playlist.with_tracks(self.load_tracks(playlist_id))

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
        """Create a new playlist owned by the authenticated user.

        Note:
            Spotify does not allow a playlist to be both public and
            collaborative; callers are expected to honour that.
        """
        user_id = self._client.current_user_id()
        payload = self._client.create_playlist(
            user_id=user_id,
            name=name,
            public=public,
            collaborative=collaborative,
            description=description,
        )
        playlist = self._mapper.playlists.map(payload)
        logger.info("Created playlist %r (%s).", playlist.name, playlist.id)
        return playlist

    def change_details(
        self,
        playlist_id: str,
        *,
        name: str | None = None,
        public: bool | None = None,
        collaborative: bool | None = None,
        description: str | None = None,
    ) -> None:
        """Change one or more of a playlist's mutable attributes.

        At least one attribute must be provided (enforced by the client).
        """
        with self._translate_not_found(playlist_id):
            self._client.change_playlist_details(
                playlist_id,
                name=name,
                public=public,
                collaborative=collaborative,
                description=description,
            )

    def unfollow(self, playlist_id: str) -> None:
        """Unfollow the playlist (Spotify's equivalent of deleting it)."""
        with self._translate_not_found(playlist_id):
            self._client.unfollow_playlist(playlist_id)
        logger.info("Unfollowed playlist %s.", playlist_id)

    # ------------------------------------------------------------------ #
    # Track membership
    # ------------------------------------------------------------------ #

    def add_tracks(self, playlist_id: str, track_uris: Sequence[str]) -> int:
        """Append tracks to a playlist, batched per the API limit.

        Returns:
            The number of URIs submitted.
        """
        uris = list(track_uris)
        with self._translate_not_found(playlist_id):
            for batch in self._chunk(uris, self._limits.playlist_modify_batch):
                self._client.playlist_add_items(playlist_id, batch)
        if uris:
            logger.debug("Added %d track(s) to playlist %s.", len(uris), playlist_id)
        return len(uris)

    def remove_tracks(self, playlist_id: str, track_uris: Sequence[str]) -> int:
        """Remove all occurrences of the given tracks from a playlist, batched.

        Returns:
            The number of URIs submitted.
        """
        uris = list(track_uris)
        with self._translate_not_found(playlist_id):
            for batch in self._chunk(uris, self._limits.playlist_modify_batch):
                self._client.playlist_remove_items(playlist_id, batch)
        if uris:
            logger.debug("Removed %d track(s) from playlist %s.", len(uris), playlist_id)
        return len(uris)

    def replace_tracks(self, playlist_id: str, track_uris: Sequence[str]) -> int:
        """Replace a playlist's entire contents with ``track_uris``.

        Spotify's replace endpoint accepts at most one batch, so for longer lists
        this clears-and-sets the first batch via replace and appends the rest via
        add. Passing an empty sequence clears the playlist.

        Returns:
            The number of URIs the playlist now contains.
        """
        uris = list(track_uris)
        batch_size = self._limits.playlist_modify_batch
        with self._translate_not_found(playlist_id):
            # Replace with the first batch (also clears any existing items).
            self._client.playlist_replace_items(playlist_id, uris[:batch_size])
            # Append any remainder in subsequent batches.
            for batch in self._chunk(uris[batch_size:], batch_size):
                self._client.playlist_add_items(playlist_id, batch)
        logger.debug("Replaced playlist %s with %d track(s).", playlist_id, len(uris))
        return len(uris)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    @contextmanager
    def _translate_not_found(self, playlist_id: str) -> Iterator[None]:
        """Translate a ``404`` from Spotify into :class:`PlaylistNotFoundError`."""
        try:
            yield
        except RequestFailedError as exc:
            if exc.http_status == 404:
                raise PlaylistNotFoundError(playlist_id) from exc
            raise

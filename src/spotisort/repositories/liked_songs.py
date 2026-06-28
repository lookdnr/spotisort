"""Repository for the user's liked songs (saved tracks)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from spotisort.models import SavedTrack
from spotisort.repositories.base import Repository

logger = logging.getLogger(__name__)

__all__ = ["LikedSongsRepository"]


class LikedSongsRepository(Repository):
    """Reads and modifies the set of tracks saved in the user's library.

    Pagination (for reads) and batching (for writes) are handled here against the
    configured :class:`~spotisort.config.BatchLimits`, so callers can pass an
    arbitrarily long list of ids and work with complete results.
    """

    def list_all(self) -> list[SavedTrack]:
        """Fetch every saved track, following pagination automatically.

        Returns:
            All saved tracks in Spotify's order (most recently added first),
            each paired with its ``added_at`` timestamp.
        """
        page_size = self._limits.saved_tracks_page
        items = self._iter_offset_items(
            lambda limit, offset: self._client.saved_tracks(limit=limit, offset=offset),
            page_size=page_size,
        )
        saved = [self._mapper.saved_tracks.map(item) for item in items]
        logger.debug("Fetched %d saved track(s).", len(saved))
        return saved

    def add(self, track_ids: Sequence[str]) -> int:
        """Save the given tracks to the library, batched per the API limit.

        Args:
            track_ids: Spotify track ids to save. Duplicates and ordering are
                passed through to Spotify as given.

        Returns:
            The number of ids submitted.
        """
        ids = list(track_ids)
        for batch in self._chunk(ids, self._limits.library_modify_batch):
            self._client.saved_tracks_add(batch)
        if ids:
            logger.debug("Saved %d track(s) to the library.", len(ids))
        return len(ids)

    def remove(self, track_ids: Sequence[str]) -> int:
        """Remove the given tracks from the library, batched per the API limit.

        Args:
            track_ids: Spotify track ids to remove.

        Returns:
            The number of ids submitted.
        """
        ids = list(track_ids)
        for batch in self._chunk(ids, self._limits.library_modify_batch):
            self._client.saved_tracks_delete(batch)
        if ids:
            logger.debug("Removed %d track(s) from the library.", len(ids))
        return len(ids)

    def contains(self, track_ids: Sequence[str]) -> dict[str, bool]:
        """Check, per id, whether each track is currently in the library.

        Args:
            track_ids: Spotify track ids to check.

        Returns:
            A mapping from track id to whether it is saved. The mapping reflects
            the last result seen for an id if duplicates are supplied.
        """
        ids = list(track_ids)
        result: dict[str, bool] = {}
        for batch in self._chunk(ids, self._limits.library_modify_batch):
            flags = self._client.saved_tracks_contains(batch)
            result.update(zip(batch, flags, strict=False))
        return result

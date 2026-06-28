"""Repository for fetching full artist objects (including genres)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from spotisort.models import Artist
from spotisort.repositories.base import Repository

logger = logging.getLogger(__name__)

__all__ = ["ArtistRepository"]


class ArtistRepository(Repository):
    """Fetches full :class:`Artist` objects by id.

    The artists embedded in track payloads carry no genres, so genre-aware
    features must load the full artist objects via this repository. Requests are
    batched against the configured limit.
    """

    def get_many(self, artist_ids: Sequence[str]) -> dict[str, Artist]:
        """Fetch full artists for the given ids.

        Args:
            artist_ids: Spotify artist ids. Duplicates are de-duplicated and
                empty ids (e.g. from local tracks) are ignored.

        Returns:
            A mapping from artist id to :class:`Artist`. Ids that Spotify did not
            return (unknown/invalid) are simply absent from the mapping.
        """
        unique = list(dict.fromkeys(aid for aid in artist_ids if aid))
        result: dict[str, Artist] = {}
        for batch in self._chunk(unique, self._limits.artists_batch):
            payload = self._client.artists(batch)
            for item in payload.get("artists") or []:
                if item is None:
                    continue
                artist = self._mapper.artists.map(item)
                if artist.id:
                    result[artist.id] = artist
        logger.debug("Fetched %d artist(s) for %d id(s).", len(result), len(unique))
        return result

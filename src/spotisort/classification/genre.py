"""Genre classification backed by Spotify artist genres."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from spotisort.classification.base import TrackClassifier
from spotisort.classification.taxonomy import GenreTaxonomy
from spotisort.models import Track
from spotisort.repositories import ArtistRepository

logger = logging.getLogger(__name__)

__all__ = ["ArtistGenreProvider", "GenreClassifier"]


class ArtistGenreProvider:
    """Resolves and caches artist genres, fetching them in bulk.

    Spotify only exposes genres on full artist objects, so this provider loads
    them via :class:`ArtistRepository` and caches per artist id. An artist with
    no genres (common) is cached as an empty tuple so it is not re-fetched.

    Args:
        repository: The artist data source.
    """

    def __init__(self, repository: ArtistRepository) -> None:
        self._repository = repository
        self._cache: dict[str, tuple[str, ...]] = {}

    def prime(self, artist_ids: Iterable[str]) -> None:
        """Fetch and cache genres for any ids not already cached."""
        missing = [aid for aid in dict.fromkeys(artist_ids) if aid and aid not in self._cache]
        if not missing:
            return
        fetched = self._repository.get_many(missing)
        for artist_id in missing:
            artist = fetched.get(artist_id)
            self._cache[artist_id] = artist.genres if artist is not None else ()

    def genres_for(self, artist_id: str) -> tuple[str, ...]:
        """Return cached genres for an artist, fetching on demand if needed."""
        if artist_id not in self._cache:
            self.prime([artist_id])
        return self._cache.get(artist_id, ())


class GenreClassifier(TrackClassifier):
    """Classifies a track by its primary artist's broad genre.

    Args:
        provider: Source of artist genres.
        taxonomy: Mapping of fine genres to broad buckets. Defaults to
            :class:`GenreTaxonomy` defaults.
    """

    def __init__(
        self, provider: ArtistGenreProvider, taxonomy: GenreTaxonomy | None = None
    ) -> None:
        self._provider = provider
        self._taxonomy = taxonomy or GenreTaxonomy()

    def prepare(self, tracks: Sequence[Track]) -> None:
        """Bulk-load genres for every track's primary artist."""
        artist_ids = [
            track.primary_artist.id
            for track in tracks
            if track.primary_artist is not None and track.primary_artist.id
        ]
        self._provider.prime(artist_ids)

    def classify(self, track: Track) -> str | None:
        artist = track.primary_artist
        if artist is None or not artist.id:
            return None
        genres = self._provider.genres_for(artist.id)
        if not genres:
            return None
        return self._taxonomy.bucket_for(genres)

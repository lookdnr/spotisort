"""Classification layer.

Assigns tracks to categories (currently broad genres) for grouping into
playlists. The :class:`TrackClassifier` interface keeps the grouping service
independent of *how* tracks are categorised, so a mood (or LLM-based) classifier
can be added later behind the same interface.
"""

from __future__ import annotations

from spotisort.classification.base import TrackClassifier
from spotisort.classification.genre import ArtistGenreProvider, GenreClassifier
from spotisort.classification.taxonomy import (
    DEFAULT_GENRE_RULES,
    GenreRule,
    GenreTaxonomy,
)

__all__ = [
    "DEFAULT_GENRE_RULES",
    "ArtistGenreProvider",
    "GenreClassifier",
    "GenreRule",
    "GenreTaxonomy",
    "TrackClassifier",
]

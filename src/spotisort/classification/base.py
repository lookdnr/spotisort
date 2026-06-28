"""The classifier abstraction.

A :class:`TrackClassifier` assigns each track to a single category label (or
``None`` to leave it unclassified). Grouping liked songs into playlists is driven
entirely through this interface, so new ways to categorise tracks — a mood
classifier, an LLM-backed classifier, a user-rules classifier — can be added
later without touching the grouping service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from spotisort.models import Track

__all__ = ["TrackClassifier"]


class TrackClassifier(ABC):
    """Assigns a category label to a track."""

    def prepare(self, tracks: Sequence[Track]) -> None:
        """Optionally warm up before classifying a batch of tracks.

        Implementations that need to fetch external data (e.g. artist genres)
        can bulk-load it here so that :meth:`classify` is cheap and offline. The
        default implementation does nothing.
        """
        return None

    @abstractmethod
    def classify(self, track: Track) -> str | None:
        """Return the category for ``track``, or ``None`` if it cannot be classified."""

"""The :class:`LibraryGrouper` service — group tracks into playlists by category."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from spotisort.classification import TrackClassifier
from spotisort.models import Playlist, SavedTrack
from spotisort.services.operations import LibraryOrganiser
from spotisort.services.playlists import PlaylistManager

logger = logging.getLogger(__name__)

__all__ = ["GroupOutcome", "GroupingResult", "LibraryGrouper"]


@dataclass(frozen=True, slots=True)
class GroupOutcome:
    """The result of grouping one category into a playlist.

    Attributes:
        category: The category label (and playlist name basis).
        playlist: The destination playlist.
        added: Number of tracks added to the playlist.
        removed: Number of tracks removed from the library (0 when copying).
    """

    category: str
    playlist: Playlist
    added: int
    removed: int


@dataclass(frozen=True, slots=True)
class GroupingResult:
    """The overall result of a grouping run.

    Attributes:
        groups: One outcome per category that had at least one track.
        unclassified: Tracks the classifier could not categorise; these are left
            untouched in the library.
    """

    groups: tuple[GroupOutcome, ...]
    unclassified: tuple[SavedTrack, ...]

    @property
    def total_added(self) -> int:
        """Total tracks added across all playlists."""
        return sum(outcome.added for outcome in self.groups)

    @property
    def total_removed(self) -> int:
        """Total tracks removed from the library across all groups."""
        return sum(outcome.removed for outcome in self.groups)


class LibraryGrouper:
    """Groups saved tracks into playlists according to a classifier.

    The grouper is classifier-agnostic: it works for genre today and for any
    future classifier (mood, LLM, rules) without change.

    Args:
        playlists: Used to create/reuse the destination playlists.
        organiser: Used to copy or move tracks (move = remove from library, with
            the verify-before-unlike safety guarantee).
    """

    def __init__(self, playlists: PlaylistManager, organiser: LibraryOrganiser) -> None:
        self._playlists = playlists
        self._organiser = organiser

    def group(
        self,
        tracks: Iterable[SavedTrack],
        classifier: TrackClassifier,
        *,
        remove_from_library: bool = True,
        name_template: str = "{category}",
    ) -> GroupingResult:
        """Classify ``tracks`` and route each category into its own playlist.

        Args:
            tracks: The saved tracks to group.
            classifier: Assigns each track to a category (or ``None`` to skip).
            remove_from_library: When ``True`` (default) tracks are moved
                (removed from Liked Songs); when ``False`` they are copied.
            name_template: Format string for the playlist name; ``{category}`` is
                substituted with the category label.

        Returns:
            A :class:`GroupingResult` summarising what happened.
        """
        saved = list(tracks)
        classifier.prepare([item.track for item in saved])

        buckets: dict[str, list[SavedTrack]] = {}
        unclassified: list[SavedTrack] = []
        for item in saved:
            category = classifier.classify(item.track)
            if category is None:
                unclassified.append(item)
            else:
                buckets.setdefault(category, []).append(item)

        outcomes: list[GroupOutcome] = []
        for category in sorted(buckets):
            group_tracks = buckets[category]
            name = name_template.format(category=category)
            playlist = self._playlists.get_or_create(name)
            if remove_from_library:
                result = self._organiser.move_to_playlist(group_tracks, playlist)
                outcomes.append(
                    GroupOutcome(category, result.playlist, result.added, result.removed)
                )
            else:
                added = self._organiser.copy_to_playlist(group_tracks, playlist)
                outcomes.append(GroupOutcome(category, playlist, added, 0))

        logger.info(
            "Grouped %d track(s) into %d playlist(s); %d unclassified.",
            sum(len(items) for items in buckets.values()),
            len(outcomes),
            len(unclassified),
        )
        return GroupingResult(tuple(outcomes), tuple(unclassified))

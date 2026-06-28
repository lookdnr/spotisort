"""Tests for the :class:`LibraryGrouper` service."""

from __future__ import annotations

from spotisort.classification import TrackClassifier
from spotisort.models import Track
from spotisort.services import (
    LibraryGrouper,
    LibraryOrganiser,
    PlaylistManager,
    SpotifyLibrary,
)
from tests.test_services import FakeLikedRepository, FakePlaylistRepository, make_saved


class StubClassifier(TrackClassifier):
    """Classifies by a fixed track-id -> category mapping."""

    def __init__(self, mapping: dict[str, str | None]) -> None:
        self._mapping = mapping
        self.prepared = False

    def prepare(self, tracks: list[Track]) -> None:  # type: ignore[override]
        self.prepared = True

    def classify(self, track: Track) -> str | None:
        return self._mapping.get(track.id)


def _grouper(liked: FakeLikedRepository, playlists: FakePlaylistRepository) -> LibraryGrouper:
    manager = PlaylistManager(playlists)
    organiser = LibraryOrganiser(SpotifyLibrary(liked), manager)
    return LibraryGrouper(manager, organiser)


def test_group_moves_into_per_category_playlists() -> None:
    saved = [make_saved("t1"), make_saved("t2"), make_saved("t3")]
    liked = FakeLikedRepository(list(saved))
    playlists = FakePlaylistRepository([], landing=tuple(s.track for s in saved))
    grouper = _grouper(liked, playlists)
    stub = StubClassifier({"t1": "Rock", "t2": "Rock", "t3": None})

    result = grouper.group(saved, stub, remove_from_library=True)

    assert stub.prepared is True
    assert result.total_added == 2
    assert {outcome.category for outcome in result.groups} == {"Rock"}
    assert [s.id for s in result.unclassified] == ["t3"]
    assert liked.removed == ["t1", "t2"]


def test_group_keep_copies_without_removing() -> None:
    saved = [make_saved("t1")]
    liked = FakeLikedRepository(list(saved))
    playlists = FakePlaylistRepository([], landing=(saved[0].track,))
    grouper = _grouper(liked, playlists)
    stub = StubClassifier({"t1": "Jazz"})

    result = grouper.group(saved, stub, remove_from_library=False)

    assert result.total_added == 1
    assert result.total_removed == 0
    assert liked.removed == []


def test_group_applies_name_template() -> None:
    saved = [make_saved("t1")]
    liked = FakeLikedRepository(list(saved))
    playlists = FakePlaylistRepository([], landing=(saved[0].track,))
    grouper = _grouper(liked, playlists)
    stub = StubClassifier({"t1": "Rock"})

    result = grouper.group(
        saved, stub, remove_from_library=False, name_template="Genre: {category}"
    )

    assert result.groups[0].playlist.name == "Genre: Rock"

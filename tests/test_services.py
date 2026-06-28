"""Tests for the service layer (library, playlists, operations)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest

from spotisort.models import Album, Artist, Playlist, SavedTrack, Track
from spotisort.services import (
    LibraryOrganiser,
    MoveVerificationError,
    PlaylistManager,
    SpotifyLibrary,
)

# --------------------------------------------------------------------------- #
# Helpers / fakes
# --------------------------------------------------------------------------- #


def make_saved(
    track_id: str,
    *,
    artist: str = "Artist",
    album: str = "Album",
    year: int = 2000,
    added: datetime | None = None,
) -> SavedTrack:
    track = Track(
        id=track_id,
        name=f"Song {track_id}",
        artists=(Artist(id="a", name=artist),),
        album=Album(id="al", name=album, release_date=str(year), release_date_precision="year"),
        uri=f"spotify:track:{track_id}",
    )
    return SavedTrack(track=track, added_at=added or datetime(2020, 1, 1, tzinfo=UTC))


class FakeLikedRepository:
    def __init__(self, data: list[SavedTrack]) -> None:
        self._data = data
        self.load_count = 0
        self.added: list[str] = []
        self.removed: list[str] = []

    def list_all(self) -> list[SavedTrack]:
        self.load_count += 1
        return list(self._data)

    def add(self, ids: Sequence[str]) -> int:
        self.added.extend(ids)
        return len(list(ids))

    def remove(self, ids: Sequence[str]) -> int:
        self.removed.extend(ids)
        return len(list(ids))

    def contains(self, ids: Sequence[str]) -> dict[str, bool]:
        present = {s.track.id for s in self._data}
        return {i: i in present for i in ids}


class FakePlaylistRepository:
    def __init__(self, playlists: list[Playlist], landing: tuple[Track, ...] = ()) -> None:
        self._playlists = playlists
        self._landing = landing
        self.created: list[str] = []
        self.added: dict[str, list[str]] = {}

    def list_all(self) -> list[Playlist]:
        return list(self._playlists)

    def get(self, playlist_id: str) -> Playlist:
        return Playlist(id=playlist_id, name="Dest")

    def get_with_tracks(self, playlist_id: str) -> Playlist:
        return Playlist(id=playlist_id, name="Dest", tracks=self._landing)

    def create(
        self, name: str, *, public: bool, collaborative: bool, description: str | None
    ) -> Playlist:
        self.created.append(name)
        return Playlist(id="created", name=name)

    def change_details(self, playlist_id: str, **kwargs: object) -> None:
        self.last_change = (playlist_id, kwargs)

    def unfollow(self, playlist_id: str) -> None:
        self.unfollowed = playlist_id

    def add_tracks(self, playlist_id: str, uris: Sequence[str]) -> int:
        self.added.setdefault(playlist_id, []).extend(uris)
        return len(list(uris))

    def replace_tracks(self, playlist_id: str, uris: Sequence[str]) -> int:
        return len(list(uris))


# --------------------------------------------------------------------------- #
# SpotifyLibrary
# --------------------------------------------------------------------------- #


def test_library_caches_until_refresh() -> None:
    repo = FakeLikedRepository([make_saved("t1")])
    library = SpotifyLibrary(repo)

    library.all_tracks()
    library.all_tracks()

    assert repo.load_count == 1
    library.refresh()
    assert repo.load_count == 2


def test_library_filters() -> None:
    data = [
        make_saved("t1", artist="Radiohead", year=1997,
                   added=datetime(2020, 1, 1, tzinfo=UTC)),
        make_saved("t2", artist="Radiohead", year=2000,
                   added=datetime(2022, 6, 1, tzinfo=UTC)),
        make_saved("t3", artist="Aphex Twin", album="Drukqs", year=2001,
                   added=datetime(2023, 1, 1, tzinfo=UTC)),
    ]
    library = SpotifyLibrary(FakeLikedRepository(data))

    assert [s.id for s in library.before(date(2021, 1, 1))] == ["t1"]
    assert [s.id for s in library.after(date(2021, 1, 1))] == ["t2", "t3"]
    assert {s.id for s in library.by_artist("radiohead")} == {"t1", "t2"}
    assert [s.id for s in library.by_album("Drukqs")] == ["t3"]
    assert [s.id for s in library.by_year(2001)] == ["t3"]
    assert [s.id for s in library.search("aphex")] == ["t3"]
    assert library.search("   ") == []


def test_library_like_invalidates_cache() -> None:
    repo = FakeLikedRepository([make_saved("t1")])
    library = SpotifyLibrary(repo)
    library.all_tracks()

    assert library.like([make_saved("t9")]) == 1
    assert library.is_loaded is False
    assert repo.added == ["t9"]


# --------------------------------------------------------------------------- #
# PlaylistManager
# --------------------------------------------------------------------------- #


def test_get_or_create_reuses_existing() -> None:
    repo = FakePlaylistRepository([Playlist(id="p1", name="Workout")])
    manager = PlaylistManager(repo)

    result = manager.get_or_create("workout")

    assert result.id == "p1"
    assert repo.created == []


def test_get_or_create_creates_when_absent() -> None:
    repo = FakePlaylistRepository([])
    manager = PlaylistManager(repo)

    result = manager.get_or_create("New")

    assert result.name == "New"
    assert repo.created == ["New"]


def test_add_tracks_resolves_uris() -> None:
    repo = FakePlaylistRepository([])
    manager = PlaylistManager(repo)
    track = make_saved("t1").track

    manager.add_tracks("p1", [track, "rawid", "spotify:track:abc"])

    assert repo.added["p1"] == ["spotify:track:t1", "spotify:track:rawid", "spotify:track:abc"]


# --------------------------------------------------------------------------- #
# LibraryOrganiser
# --------------------------------------------------------------------------- #


def test_move_success_removes_from_library() -> None:
    moved = [make_saved("t1"), make_saved("t2")]
    liked = FakeLikedRepository(list(moved))
    playlists = FakePlaylistRepository([], landing=(moved[0].track, moved[1].track))
    organiser = LibraryOrganiser(SpotifyLibrary(liked), PlaylistManager(playlists))

    result = organiser.move_to_playlist(moved, "p1")

    assert result.added == 2
    assert result.removed == 2
    assert liked.removed == ["t1", "t2"]


def test_move_aborts_when_verification_fails() -> None:
    moved = [make_saved("t1"), make_saved("t2")]
    liked = FakeLikedRepository(list(moved))
    playlists = FakePlaylistRepository([], landing=())  # nothing landed
    organiser = LibraryOrganiser(SpotifyLibrary(liked), PlaylistManager(playlists))

    with pytest.raises(MoveVerificationError):
        organiser.move_to_playlist(moved, "p1")

    assert liked.removed == []  # library untouched


def test_copy_leaves_library_untouched() -> None:
    tracks = [make_saved("t1")]
    liked = FakeLikedRepository(list(tracks))
    playlists = FakePlaylistRepository([])
    organiser = LibraryOrganiser(SpotifyLibrary(liked), PlaylistManager(playlists))

    assert organiser.copy_to_playlist(tracks, "p1") == 1
    assert liked.removed == []

"""Tests for the SQLite cache and the caching repositories."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from spotisort.cache import ArtistGenreCache, Database, LibraryCache
from spotisort.cache.serialization import decode_saved_track, encode_saved_track
from spotisort.models import Artist, SavedTrack, Track
from spotisort.repositories import CachedArtistRepository, CachedLikedSongsRepository
from tests.test_services import make_saved

# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def test_saved_track_serialization_roundtrip() -> None:
    saved = make_saved("t1", artist="Aphex Twin", album="Drukqs", year=2001)
    restored = decode_saved_track(json.loads(json.dumps(encode_saved_track(saved))))
    assert restored == saved


def test_serialization_roundtrip_without_album() -> None:
    track = Track(id="t1", name="Local", artists=(Artist(id="a", name="A"),), album=None)
    saved = SavedTrack(track=track, added_at=datetime(2020, 1, 1, tzinfo=UTC))
    restored = decode_saved_track(json.loads(json.dumps(encode_saved_track(saved))))
    assert restored == saved
    assert restored.track.album is None


# --------------------------------------------------------------------------- #
# LibraryCache
# --------------------------------------------------------------------------- #


def test_library_cache_miss_then_save_and_load(tmp_path: Path) -> None:
    cache = LibraryCache(Database(tmp_path / "c.db"))
    assert cache.load() is None  # never synced -> miss
    assert cache.is_fresh(timedelta(days=1)) is False

    cache.save([make_saved("t1"), make_saved("t2")])
    loaded = cache.load()
    assert loaded is not None
    assert [s.id for s in loaded] == ["t1", "t2"]
    assert cache.is_fresh(timedelta(days=1)) is True
    assert cache.is_fresh(None) is True


def test_library_cache_empty_library_is_not_a_miss(tmp_path: Path) -> None:
    cache = LibraryCache(Database(tmp_path / "c.db"))
    cache.save([])
    # An empty library (synced, zero tracks) is distinct from "never synced".
    assert cache.load() == []


def test_library_cache_clear_resets_to_miss(tmp_path: Path) -> None:
    cache = LibraryCache(Database(tmp_path / "c.db"))
    cache.save([make_saved("t1")])
    cache.clear()
    assert cache.load() is None


def test_library_cache_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    LibraryCache(Database(path)).save([make_saved("t1")])
    reopened = LibraryCache(Database(path))  # simulates a new process
    loaded = reopened.load()
    assert loaded is not None
    assert [s.id for s in loaded] == ["t1"]


# --------------------------------------------------------------------------- #
# ArtistGenreCache
# --------------------------------------------------------------------------- #


def test_artist_cache_put_get_clear(tmp_path: Path) -> None:
    cache = ArtistGenreCache(Database(tmp_path / "c.db"))
    cache.put_many([Artist(id="a1", name="A1", genres=("techno",))])
    got = cache.get_many(["a1", "a2"])
    assert set(got) == {"a1"}
    assert got["a1"].genres == ("techno",)
    cache.clear()
    assert cache.get_many(["a1"]) == {}


# --------------------------------------------------------------------------- #
# Caching repositories
# --------------------------------------------------------------------------- #


class FakeLikedDelegate:
    def __init__(self, data: list[SavedTrack]) -> None:
        self._data = data
        self.list_calls = 0
        self.added: list[str] = []
        self.removed: list[str] = []

    def list_all(self) -> list[SavedTrack]:
        self.list_calls += 1
        return list(self._data)

    def add(self, track_ids: Sequence[str]) -> int:
        self.added.extend(track_ids)
        return len(list(track_ids))

    def remove(self, track_ids: Sequence[str]) -> int:
        self.removed.extend(track_ids)
        return len(list(track_ids))

    def contains(self, track_ids: Sequence[str]) -> dict[str, bool]:
        return dict.fromkeys(track_ids, True)


def test_cached_liked_repo_cold_then_warm_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    delegate = FakeLikedDelegate([make_saved("t1"), make_saved("t2")])
    repo = CachedLikedSongsRepository(delegate, LibraryCache(Database(path)), ttl=None)

    assert [s.id for s in repo.list_all()] == ["t1", "t2"]  # cold: hits delegate
    assert delegate.list_calls == 1

    # A fresh repo + fresh delegate sharing the same DB must read from cache.
    cold_delegate = FakeLikedDelegate([])
    warm = CachedLikedSongsRepository(cold_delegate, LibraryCache(Database(path)), ttl=None)
    assert [s.id for s in warm.list_all()] == ["t1", "t2"]
    assert cold_delegate.list_calls == 0


def test_cached_liked_repo_writes_invalidate(tmp_path: Path) -> None:
    delegate = FakeLikedDelegate([make_saved("t1")])
    repo = CachedLikedSongsRepository(delegate, LibraryCache(Database(tmp_path / "c.db")), ttl=None)

    repo.list_all()
    repo.list_all()
    assert delegate.list_calls == 1  # second read served from cache

    repo.add(["x"])  # write invalidates the cache
    repo.list_all()
    assert delegate.list_calls == 2
    assert delegate.added == ["x"]


def test_cached_liked_repo_contains_always_live(tmp_path: Path) -> None:
    delegate = FakeLikedDelegate([make_saved("t1")])
    repo = CachedLikedSongsRepository(delegate, LibraryCache(Database(tmp_path / "c.db")), ttl=None)
    assert repo.contains(["t1"]) == {"t1": True}


class FakeArtistDelegate:
    def __init__(self, artists: dict[str, Artist]) -> None:
        self._artists = artists
        self.calls: list[list[str]] = []

    def get_many(self, artist_ids: Sequence[str]) -> dict[str, Artist]:
        self.calls.append(list(artist_ids))
        return {aid: self._artists[aid] for aid in artist_ids if aid in self._artists}


def test_cached_artist_repo_fetches_only_misses(tmp_path: Path) -> None:
    delegate = FakeArtistDelegate(
        {
            "a1": Artist(id="a1", name="A1", genres=("techno",)),
            "a3": Artist(id="a3", name="A3", genres=("jazz",)),
        }
    )
    repo = CachedArtistRepository(delegate, ArtistGenreCache(Database(tmp_path / "c.db")))

    first = repo.get_many(["a1"])
    assert set(first) == {"a1"}
    assert delegate.calls == [["a1"]]

    # a1 is now cached; only a3 should be fetched on the second call.
    second = repo.get_many(["a1", "a3"])
    assert set(second) == {"a1", "a3"}
    assert delegate.calls == [["a1"], ["a3"]]

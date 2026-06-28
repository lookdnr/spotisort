"""Tests for the repository layer (pagination + batching)."""

from __future__ import annotations

import pytest

from spotisort.api.exceptions import PlaylistNotFoundError
from spotisort.config import Settings
from spotisort.repositories import (
    ArtistRepository,
    LikedSongsRepository,
    PlaylistRepository,
)
from tests.conftest import (
    FakeSpotifyClient,
    artist_payload,
    playlist_item,
    playlist_payload,
    saved_item,
    track_payload,
)


def test_liked_list_all_paginates(settings: Settings) -> None:
    saved = [saved_item(track_id=f"t{i}", name=f"n{i}") for i in range(5)]
    client = FakeSpotifyClient(saved=saved)
    repo = LikedSongsRepository(client, limits=settings.batch_limits)

    result = repo.list_all()

    assert [s.track.id for s in result] == [f"t{i}" for i in range(5)]


def test_liked_add_batches_by_limit(settings: Settings) -> None:
    client = FakeSpotifyClient()
    repo = LikedSongsRepository(client, limits=settings.batch_limits)

    count = repo.add([f"t{i}" for i in range(5)])

    assert count == 5
    # page size is 2, so 5 ids -> batches of 2, 2, 1
    assert [len(batch) for batch in client.calls_of("add")] == [2, 2, 1]


def test_liked_contains_returns_mapping(settings: Settings) -> None:
    client = FakeSpotifyClient(contains={"t1": True})
    repo = LikedSongsRepository(client, limits=settings.batch_limits)

    result = repo.contains(["t1", "t2"])

    assert result == {"t1": True, "t2": False}


def test_playlist_load_tracks_paginates(settings: Settings) -> None:
    items = [playlist_item(track_payload(track_id=f"t{i}", name=f"n{i}")) for i in range(5)]
    client = FakeSpotifyClient(
        playlists=[playlist_payload(playlist_id="p1")],
        playlist_items={"p1": items},
    )
    repo = PlaylistRepository(client, limits=settings.batch_limits)

    playlist = repo.get_with_tracks("p1")

    assert playlist.is_loaded
    assert playlist.track_count == 5


def test_playlist_replace_orchestrates_replace_then_add(settings: Settings) -> None:
    client = FakeSpotifyClient(playlists=[playlist_payload(playlist_id="p1")])
    repo = PlaylistRepository(client, limits=settings.batch_limits)

    repo.replace_tracks("p1", [f"spotify:track:t{i}" for i in range(5)])

    # batch size 2: replace(2) then add(2), add(1)
    assert [len(b) for b in client.calls_of("playlist_replace")] == [2]
    assert [len(b) for b in client.calls_of("playlist_add")] == [2, 1]


def test_playlist_get_missing_raises_not_found(settings: Settings) -> None:
    client = FakeSpotifyClient(playlists=[])
    repo = PlaylistRepository(client, limits=settings.batch_limits)

    with pytest.raises(PlaylistNotFoundError):
        repo.get("missing")


def test_playlist_create_uses_current_user(settings: Settings) -> None:
    client = FakeSpotifyClient(user_id="me")
    repo = PlaylistRepository(client, limits=settings.batch_limits)

    repo.create("New", public=True)

    assert client.calls_of("create") == [{"user_id": "me", "name": "New"}]


def test_artist_get_many_batches_dedups_and_skips_unknown(settings: Settings) -> None:
    client = FakeSpotifyClient(
        artists={
            "a1": artist_payload("a1", genres=["rock"]),
            "a2": artist_payload("a2", genres=["pop"]),
            "a3": artist_payload("a3", genres=["jazz"]),
            # "a4" intentionally absent -> Spotify returns null for it.
        }
    )
    repo = ArtistRepository(client, limits=settings.batch_limits)  # artists_batch defaults to 50

    result = repo.get_many(["a1", "a1", "a2", "a3", "a4", ""])

    assert set(result) == {"a1", "a2", "a3"}
    assert result["a2"].genres == ("pop",)
    # Deduplicated + empty removed -> one request of 4 ids.
    assert client.calls_of("artists") == [["a1", "a2", "a3", "a4"]]

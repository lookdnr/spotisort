"""Tests for :mod:`spotisort.mapping`."""

from __future__ import annotations

from datetime import UTC

import pytest

from spotisort.api.exceptions import MappingError
from spotisort.mapping import SpotifyMapper
from tests.conftest import (
    artist_payload,
    playlist_item,
    playlist_payload,
    saved_item,
    track_payload,
)


@pytest.fixture
def mapper() -> SpotifyMapper:
    return SpotifyMapper()


def test_saved_track_mapping(mapper: SpotifyMapper) -> None:
    saved = mapper.saved_tracks.map(saved_item(added_at="2021-05-01T10:00:00Z"))

    assert saved.track.name == "Song"
    assert saved.track.release_year == 1999
    assert saved.added_at.tzinfo is not None
    assert saved.added_at.astimezone(UTC).year == 2021


def test_playlist_metadata_mapping(mapper: SpotifyMapper) -> None:
    playlist = mapper.playlists.map(playlist_payload(name="My Mix", total=42))

    assert playlist.name == "My Mix"
    assert playlist.owner_name == "Owner"
    assert playlist.total_tracks == 42
    assert playlist.is_loaded is False


def test_map_items_skips_unavailable_tracks(mapper: SpotifyMapper) -> None:
    items = [
        playlist_item(track_payload(track_id="t1", name="A")),
        playlist_item(None),
        playlist_item(track_payload(track_id="t2", name="B")),
    ]
    tracks = mapper.playlists.map_items(items)

    assert [track.name for track in tracks] == ["A", "B"]


def test_missing_name_raises_mapping_error(mapper: SpotifyMapper) -> None:
    with pytest.raises(MappingError):
        mapper.tracks.map({"id": "t1"})


def test_bad_timestamp_raises_mapping_error(mapper: SpotifyMapper) -> None:
    with pytest.raises(MappingError):
        mapper.saved_tracks.map({"added_at": "not-a-date", "track": track_payload()})


def test_full_artist_maps_genres(mapper: SpotifyMapper) -> None:
    payload = artist_payload("a1", "Daft Punk", genres=["french house", "filter house"])
    artist = mapper.artists.map(payload)
    assert artist.genres == ("french house", "filter house")


def test_embedded_artist_has_no_genres(mapper: SpotifyMapper) -> None:
    # Artists embedded in track payloads carry no genres.
    track = mapper.tracks.map(track_payload())
    assert track.artists[0].genres == ()

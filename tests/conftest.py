"""Shared test fixtures, payload builders and an in-memory fake client."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from spotisort.api.exceptions import RequestFailedError
from spotisort.config import BatchLimits, Settings

# --------------------------------------------------------------------------- #
# Payload builders (shaped like Spotify Web API responses)
# --------------------------------------------------------------------------- #


def track_payload(
    track_id: str = "t1",
    name: str = "Song",
    *,
    artists: Sequence[tuple[str, str]] | None = None,
    album_name: str = "Album",
    release_date: str = "1999",
    uri: str | None = None,
    with_album: bool = True,
) -> dict[str, Any]:
    """Build a raw track payload."""
    payload: dict[str, Any] = {
        "id": track_id,
        "name": name,
        "uri": uri or f"spotify:track:{track_id}",
        "duration_ms": 200000,
        "explicit": False,
        "artists": [{"id": aid, "name": aname} for aid, aname in (artists or [("a1", "Artist")])],
    }
    if with_album:
        payload["album"] = {
            "id": "al1",
            "name": album_name,
            "release_date": release_date,
            "release_date_precision": "year",
            "artists": [{"id": "a1", "name": "Artist"}],
        }
    return payload


def saved_item(added_at: str = "2021-01-01T00:00:00Z", **track_kwargs: Any) -> dict[str, Any]:
    """Build a raw saved-track item (from GET /me/tracks)."""
    return {"added_at": added_at, "track": track_payload(**track_kwargs)}


def playlist_payload(
    playlist_id: str = "p1",
    name: str = "Playlist",
    *,
    total: int = 0,
) -> dict[str, Any]:
    """Build a raw playlist payload (metadata)."""
    return {
        "id": playlist_id,
        "name": name,
        "snapshot_id": "snap",
        "collaborative": False,
        "public": True,
        "owner": {"id": "u1", "display_name": "Owner"},
        "tracks": {"total": total},
    }


def playlist_item(track: dict[str, Any] | None) -> dict[str, Any]:
    """Build a raw playlist item, optionally with a null (unavailable) track."""
    return {"track": track}


def artist_payload(
    artist_id: str = "a1",
    name: str = "Artist",
    *,
    genres: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a raw full-artist payload (as returned by GET /v1/artists)."""
    return {"id": artist_id, "name": name, "genres": list(genres)}


# --------------------------------------------------------------------------- #
# Fake client
# --------------------------------------------------------------------------- #


class FakeSpotifyClient:
    """In-memory stand-in for :class:`~spotisort.api.client.SpotifyClient`.

    Serves configured data with real offset pagination and records every
    mutating call so tests can assert on batching behaviour.
    """

    def __init__(
        self,
        *,
        saved: list[dict[str, Any]] | None = None,
        playlists: list[dict[str, Any]] | None = None,
        playlist_items: dict[str, list[dict[str, Any]]] | None = None,
        contains: dict[str, bool] | None = None,
        artists: dict[str, dict[str, Any]] | None = None,
        user_id: str = "user-1",
    ) -> None:
        self._saved = list(saved or [])
        self._playlists = list(playlists or [])
        self._playlist_items = dict(playlist_items or {})
        self._contains = dict(contains or {})
        self._artists = dict(artists or {})
        self._user_id = user_id
        self.calls: list[tuple[str, Any]] = []

    # -- user --
    def current_user_id(self) -> str:
        return self._user_id

    # -- artists --
    def artists(self, artist_ids: Sequence[str]) -> dict[str, Any]:
        self.calls.append(("artists", list(artist_ids)))
        return {"artists": [self._artists.get(artist_id) for artist_id in artist_ids]}

    # -- saved tracks --
    def saved_tracks(self, *, limit: int, offset: int) -> dict[str, Any]:
        return _page(self._saved, limit, offset)

    def saved_tracks_add(self, track_ids: Sequence[str]) -> None:
        self.calls.append(("add", list(track_ids)))

    def saved_tracks_delete(self, track_ids: Sequence[str]) -> None:
        self.calls.append(("delete", list(track_ids)))

    def saved_tracks_contains(self, track_ids: Sequence[str]) -> list[bool]:
        self.calls.append(("contains", list(track_ids)))
        return [self._contains.get(track_id, False) for track_id in track_ids]

    # -- playlists --
    def current_user_playlists(self, *, limit: int, offset: int) -> dict[str, Any]:
        return _page(self._playlists, limit, offset)

    def playlist(self, playlist_id: str, *, fields: str | None = None) -> dict[str, Any]:
        for payload in self._playlists:
            if payload["id"] == playlist_id:
                return payload
        raise RequestFailedError("not found", http_status=404)

    def playlist_items(
        self, playlist_id: str, *, limit: int, offset: int, fields: str | None = None
    ) -> dict[str, Any]:
        if playlist_id not in self._playlist_items:
            raise RequestFailedError("not found", http_status=404)
        return _page(self._playlist_items[playlist_id], limit, offset)

    def create_playlist(
        self,
        *,
        user_id: str,
        name: str,
        public: bool,
        collaborative: bool,
        description: str | None,
    ) -> dict[str, Any]:
        self.calls.append(("create", {"user_id": user_id, "name": name}))
        return playlist_payload(playlist_id="created", name=name)

    def change_playlist_details(self, playlist_id: str, **changes: Any) -> None:
        self.calls.append(("change", {"id": playlist_id, **changes}))

    def playlist_add_items(
        self, playlist_id: str, track_uris: Sequence[str], *, position: int | None = None
    ) -> dict[str, Any]:
        self.calls.append(("playlist_add", list(track_uris)))
        return {"snapshot_id": "snap"}

    def playlist_remove_items(
        self, playlist_id: str, track_uris: Sequence[str]
    ) -> dict[str, Any]:
        self.calls.append(("playlist_remove", list(track_uris)))
        return {"snapshot_id": "snap"}

    def playlist_replace_items(
        self, playlist_id: str, track_uris: Sequence[str]
    ) -> dict[str, Any]:
        self.calls.append(("playlist_replace", list(track_uris)))
        return {"snapshot_id": "snap"}

    def unfollow_playlist(self, playlist_id: str) -> None:
        self.calls.append(("unfollow", playlist_id))

    # -- helpers for assertions --
    def calls_of(self, kind: str) -> list[Any]:
        """Return the payloads of every recorded call of the given kind."""
        return [payload for name, payload in self.calls if name == kind]


def _page(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    """Build a Spotify-style paging object for a slice of ``items``."""
    window = items[offset : offset + limit]
    has_more = offset + limit < len(items)
    return {"items": window, "total": len(items), "next": "more" if has_more else None}


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        token_cache_path=tmp_path / ".cache",
        batch_limits=BatchLimits(
            saved_tracks_page=2,
            playlist_items_page=2,
            playlists_page=2,
            playlist_modify_batch=2,
            library_modify_batch=2,
        ),
    )

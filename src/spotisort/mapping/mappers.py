"""Conversion of raw Spotify payloads into domain models.

This module is the boundary between the API's JSON shape and the rest of the
application. Each mapper turns one kind of raw payload into one kind of model and
raises :class:`~spotisort.api.exceptions.MappingError` when a payload is missing
required fields or has an unexpected shape.

Mappers are small, stateless and composable: a :class:`TrackMapper` delegates to
an :class:`AlbumMapper` and :class:`ArtistMapper`, and so on. They are wired
together by constructor injection (with sensible defaults), and
:class:`SpotifyMapper` provides a ready-assembled set for the repository layer.

Keeping this logic here — rather than as ``from_dict`` classmethods on the
models — means the models stay free of any Spotify knowledge, so a future SQLite
cache or a direct-HTTP backend only needs new mappers, not new models.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from spotisort.api.exceptions import MappingError
from spotisort.models import Album, Artist, Playlist, SavedTrack, Track

__all__ = [
    "AlbumMapper",
    "ArtistMapper",
    "PlaylistMapper",
    "SavedTrackMapper",
    "SpotifyMapper",
    "TrackMapper",
]


# --------------------------------------------------------------------------- #
# Entity mappers
# --------------------------------------------------------------------------- #


class ArtistMapper:
    """Maps raw artist payloads into :class:`Artist` models."""

    def map(self, payload: Any) -> Artist:
        data = _as_mapping(payload, context="artist")
        return Artist(
            id=_id(data),
            name=_require_str(data, "name", context="artist"),
            uri=_optional_str(data, "uri"),
            url=_spotify_url(data),
        )

    def map_many(self, payloads: Iterable[Any] | None) -> tuple[Artist, ...]:
        if not payloads:
            return ()
        return tuple(self.map(item) for item in payloads)


class AlbumMapper:
    """Maps raw album payloads into :class:`Album` models."""

    def __init__(self, artist_mapper: ArtistMapper | None = None) -> None:
        self._artists = artist_mapper or ArtistMapper()

    def map(self, payload: Any) -> Album:
        data = _as_mapping(payload, context="album")
        return Album(
            id=_id(data),
            name=_require_str(data, "name", context="album"),
            artists=self._artists.map_many(data.get("artists")),
            release_date=_optional_str(data, "release_date"),
            release_date_precision=_optional_str(data, "release_date_precision"),
            total_tracks=_optional_int(data, "total_tracks"),
            uri=_optional_str(data, "uri"),
            url=_spotify_url(data),
        )


class TrackMapper:
    """Maps raw track payloads into :class:`Track` models."""

    def __init__(
        self,
        artist_mapper: ArtistMapper | None = None,
        album_mapper: AlbumMapper | None = None,
    ) -> None:
        self._artists = artist_mapper or ArtistMapper()
        self._albums = album_mapper or AlbumMapper(self._artists)

    def map(self, payload: Any) -> Track:
        data = _as_mapping(payload, context="track")
        album_payload = data.get("album")
        album = self._albums.map(album_payload) if isinstance(album_payload, Mapping) else None
        return Track(
            id=_id(data),
            name=_require_str(data, "name", context="track"),
            artists=self._artists.map_many(data.get("artists")),
            album=album,
            duration_ms=_optional_int(data, "duration_ms") or 0,
            explicit=bool(data.get("explicit", False)),
            disc_number=_optional_int(data, "disc_number"),
            track_number=_optional_int(data, "track_number"),
            popularity=_optional_int(data, "popularity"),
            is_local=bool(data.get("is_local", False)),
            uri=_optional_str(data, "uri"),
            url=_spotify_url(data),
        )


class SavedTrackMapper:
    """Maps raw "saved track" items (from GET /me/tracks) into :class:`SavedTrack`."""

    def __init__(self, track_mapper: TrackMapper | None = None) -> None:
        self._tracks = track_mapper or TrackMapper()

    def map(self, payload: Any) -> SavedTrack:
        data = _as_mapping(payload, context="saved track")
        track = self._tracks.map(_as_mapping(data.get("track"), context="saved track 'track'"))
        added_at = _parse_datetime(data.get("added_at"), context="saved track 'added_at'")
        return SavedTrack(track=track, added_at=added_at)


class PlaylistMapper:
    """Maps raw playlist payloads and playlist items into models.

    :meth:`map` produces playlist *metadata* only (``tracks=None``); loading the
    items is a separate, paged operation handled by the repository, which then
    attaches them via :meth:`Playlist.with_tracks`.
    """

    def __init__(self, track_mapper: TrackMapper | None = None) -> None:
        self._tracks = track_mapper or TrackMapper()

    def map(self, payload: Any) -> Playlist:
        data = _as_mapping(payload, context="playlist")
        owner = data.get("owner")
        owner_map = owner if isinstance(owner, Mapping) else {}
        tracks_meta = data.get("tracks")
        total = tracks_meta.get("total") if isinstance(tracks_meta, Mapping) else None
        return Playlist(
            id=_require_str(data, "id", context="playlist"),
            name=_require_str(data, "name", context="playlist"),
            owner_id=_optional_str(owner_map, "id"),
            owner_name=_optional_str(owner_map, "display_name"),
            description=_optional_str(data, "description"),
            public=data.get("public") if isinstance(data.get("public"), bool) else None,
            collaborative=bool(data.get("collaborative", False)),
            snapshot_id=_optional_str(data, "snapshot_id"),
            total_tracks=total if isinstance(total, int) and not isinstance(total, bool) else None,
            uri=_optional_str(data, "uri"),
            url=_spotify_url(data),
            tracks=None,
        )

    def map_item(self, payload: Any) -> Track | None:
        """Map a single playlist item to a :class:`Track`.

        Returns ``None`` for items whose track is unavailable (e.g. removed from
        the catalogue), which Spotify represents as a ``null`` track.
        """
        data = _as_mapping(payload, context="playlist item")
        track_payload = data.get("track")
        if not isinstance(track_payload, Mapping):
            return None
        return self._tracks.map(track_payload)

    def map_items(self, payloads: Iterable[Any] | None) -> tuple[Track, ...]:
        """Map many playlist items, skipping any whose track is unavailable."""
        if not payloads:
            return ()
        mapped = (self.map_item(item) for item in payloads)
        return tuple(track for track in mapped if track is not None)


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #


class SpotifyMapper:
    """A pre-assembled, shared set of mappers for the repository layer.

    Wiring the mappers together once (so they reuse each other) gives the
    repositories a single, injectable dependency rather than several.
    """

    def __init__(self) -> None:
        self.artists = ArtistMapper()
        self.albums = AlbumMapper(self.artists)
        self.tracks = TrackMapper(self.artists, self.albums)
        self.saved_tracks = SavedTrackMapper(self.tracks)
        self.playlists = PlaylistMapper(self.tracks)


# --------------------------------------------------------------------------- #
# Internal extraction helpers
# --------------------------------------------------------------------------- #


def _as_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    """Return ``value`` as a mapping or raise :class:`MappingError`."""
    if not isinstance(value, Mapping):
        raise MappingError(f"Expected an object for {context}, got {type(value).__name__}.")
    return value


def _id(payload: Mapping[str, Any]) -> str:
    """Return a string id, or empty string when absent (e.g. local tracks)."""
    value = payload.get("id")
    return value if isinstance(value, str) else ""


def _require_str(payload: Mapping[str, Any], key: str, *, context: str) -> str:
    """Return a required, non-empty string field or raise :class:`MappingError`."""
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise MappingError(f"Missing or invalid {key!r} in {context}.")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    """Return a string field if present and of the right type, else ``None``."""
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    """Return an int field if present (excluding bools), else ``None``."""
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _spotify_url(payload: Mapping[str, Any]) -> str | None:
    """Extract the public Spotify URL from an ``external_urls`` object."""
    external = payload.get("external_urls")
    if isinstance(external, Mapping):
        url = external.get("spotify")
        if isinstance(url, str):
            return url
    return None


def _parse_datetime(value: Any, *, context: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware (UTC) datetime."""
    if not isinstance(value, str):
        raise MappingError(f"Missing or invalid timestamp in {context}.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MappingError(f"Could not parse timestamp {value!r} in {context}.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed

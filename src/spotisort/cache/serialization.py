"""(De)serialisation of domain models to and from the cache's JSON format.

This is spotisort's *own* stable, versioned representation of its models — not
Spotify's payload shape — and it lives entirely within the cache layer. Keeping
it here (rather than as methods on the models) keeps the domain models pure and
lets the on-disk format evolve independently behind a schema version.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from spotisort.models import Album, Artist, SavedTrack, Track

__all__ = [
    "decode_artist",
    "decode_saved_track",
    "encode_artist",
    "encode_saved_track",
]


# --------------------------------------------------------------------------- #
# Artist
# --------------------------------------------------------------------------- #


def encode_artist(artist: Artist) -> dict[str, Any]:
    return {
        "id": artist.id,
        "name": artist.name,
        "uri": artist.uri,
        "url": artist.url,
        "genres": list(artist.genres),
    }


def decode_artist(data: Mapping[str, Any]) -> Artist:
    return Artist(
        id=data["id"],
        name=data["name"],
        uri=data.get("uri"),
        url=data.get("url"),
        genres=tuple(data.get("genres") or ()),
    )


# --------------------------------------------------------------------------- #
# Album
# --------------------------------------------------------------------------- #


def encode_album(album: Album | None) -> dict[str, Any] | None:
    if album is None:
        return None
    return {
        "id": album.id,
        "name": album.name,
        "artists": [encode_artist(artist) for artist in album.artists],
        "release_date": album.release_date,
        "release_date_precision": album.release_date_precision,
        "total_tracks": album.total_tracks,
        "uri": album.uri,
        "url": album.url,
    }


def decode_album(data: Mapping[str, Any] | None) -> Album | None:
    if data is None:
        return None
    return Album(
        id=data["id"],
        name=data["name"],
        artists=tuple(decode_artist(artist) for artist in data.get("artists") or ()),
        release_date=data.get("release_date"),
        release_date_precision=data.get("release_date_precision"),
        total_tracks=data.get("total_tracks"),
        uri=data.get("uri"),
        url=data.get("url"),
    )


# --------------------------------------------------------------------------- #
# Track
# --------------------------------------------------------------------------- #


def encode_track(track: Track) -> dict[str, Any]:
    return {
        "id": track.id,
        "name": track.name,
        "artists": [encode_artist(artist) for artist in track.artists],
        "album": encode_album(track.album),
        "duration_ms": track.duration_ms,
        "explicit": track.explicit,
        "disc_number": track.disc_number,
        "track_number": track.track_number,
        "popularity": track.popularity,
        "is_local": track.is_local,
        "uri": track.uri,
        "url": track.url,
    }


def decode_track(data: Mapping[str, Any]) -> Track:
    return Track(
        id=data["id"],
        name=data["name"],
        artists=tuple(decode_artist(artist) for artist in data.get("artists") or ()),
        album=decode_album(data.get("album")),
        duration_ms=data.get("duration_ms", 0),
        explicit=data.get("explicit", False),
        disc_number=data.get("disc_number"),
        track_number=data.get("track_number"),
        popularity=data.get("popularity"),
        is_local=data.get("is_local", False),
        uri=data.get("uri"),
        url=data.get("url"),
    )


# --------------------------------------------------------------------------- #
# SavedTrack
# --------------------------------------------------------------------------- #


def encode_saved_track(saved: SavedTrack) -> dict[str, Any]:
    return {
        "added_at": saved.added_at.isoformat(),
        "track": encode_track(saved.track),
    }


def decode_saved_track(data: Mapping[str, Any]) -> SavedTrack:
    return SavedTrack(
        track=decode_track(data["track"]),
        added_at=datetime.fromisoformat(data["added_at"]),
    )

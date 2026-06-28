"""Tests for the CLI parsing and selection logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from spotisort.cli.app import _format_saved, _select_saved, build_parser, main
from spotisort.models import Album, Artist, SavedTrack, Track


def make_saved(track_id: str, artist: str, year: int) -> SavedTrack:
    track = Track(
        id=track_id,
        name=f"Song {track_id}",
        artists=(Artist(id="a", name=artist),),
        album=Album(id="al", name="Alb", release_date=str(year), release_date_precision="year"),
        uri=f"spotify:track:{track_id}",
    )
    return SavedTrack(track=track, added_at=datetime(2020, 1, 1, tzinfo=UTC))


class FakeLibrary:
    def __init__(self, data: list[SavedTrack]) -> None:
        self._data = data

    def all_tracks(self) -> list[SavedTrack]:
        return list(self._data)

    def by_artist(self, name: str) -> list[SavedTrack]:
        return [s for s in self._data if s.track.artists[0].name.casefold() == name.casefold()]

    def by_year(self, year: int) -> list[SavedTrack]:
        return [s for s in self._data if s.track.release_year == year]

    # Unused-but-required by the selection function's other branches.
    def before(self, moment: object) -> list[SavedTrack]:
        return list(self._data)

    def after(self, moment: object) -> list[SavedTrack]:
        return []

    def by_album(self, name: str) -> list[SavedTrack]:
        return list(self._data)

    def search(self, query: str) -> list[SavedTrack]:
        return list(self._data)


def test_parser_parses_filters() -> None:
    parser = build_parser()
    args = parser.parse_args(["liked", "--year", "2001", "--artist", "Aphex Twin", "--limit", "5"])
    assert args.command == "liked"
    assert args.year == 2001
    assert args.artist == "Aphex Twin"
    assert args.limit == 5


def test_move_requires_destination() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["move"])


def test_select_combines_filters_with_and() -> None:
    parser = build_parser()
    data = [
        make_saved("t1", "Aphex Twin", 2001),
        make_saved("t2", "Aphex Twin", 1999),
        make_saved("t3", "Boards of Canada", 2001),
    ]
    args = parser.parse_args(["liked", "--year", "2001", "--artist", "Aphex Twin"])

    selected = _select_saved(FakeLibrary(data), args)

    assert [s.id for s in selected] == ["t1"]


def test_format_saved_includes_year() -> None:
    line = _format_saved(make_saved("t1", "Aphex Twin", 2001))
    assert "Aphex Twin" in line
    assert "(2001)" in line


def test_main_returns_two_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    # Avoid loading any on-disk .env during the test.
    monkeypatch.setattr("spotisort.config._load_dotenv", lambda *a, **k: False)

    assert main(["playlists"]) == 2

"""Tests for the classification layer (taxonomy, provider, genre classifier)."""

from __future__ import annotations

import pytest

from spotisort.classification import ArtistGenreProvider, GenreClassifier, GenreTaxonomy
from spotisort.config import Settings
from spotisort.models import Artist, Track
from spotisort.repositories import ArtistRepository
from tests.conftest import FakeSpotifyClient, artist_payload


@pytest.fixture
def taxonomy() -> GenreTaxonomy:
    return GenreTaxonomy()


@pytest.mark.parametrize(
    ("genre", "expected"),
    [
        ("uk garage", "Electronic"),
        ("garage rock", "Rock"),
        ("pop punk", "Punk"),
        ("death metal", "Metal"),
        ("conscious hip hop", "Hip-Hop"),
        ("neo soul", "R&B & Soul"),
        ("something obscure", None),
    ],
)
def test_taxonomy_bucket(taxonomy: GenreTaxonomy, genre: str, expected: str | None) -> None:
    assert taxonomy.bucket(genre) == expected


def test_taxonomy_bucket_for_majority(taxonomy: GenreTaxonomy) -> None:
    # grunge + psychedelic rock -> Rock (2), techno -> Electronic (1): Rock wins.
    assert taxonomy.bucket_for(["grunge", "psychedelic rock", "techno"]) == "Rock"
    # "indie" is tested before "rock", so indie genres bucket to Indie & Alternative.
    assert taxonomy.bucket_for(["indie rock", "indie pop"]) == "Indie & Alternative"
    assert taxonomy.bucket_for([]) is None
    assert taxonomy.bucket_for(["unknown"]) is None


def _track(track_id: str, artist_id: str) -> Track:
    return Track(id=track_id, name="x", artists=(Artist(id=artist_id, name="A"),))


def test_provider_caches_and_batches(settings: Settings) -> None:
    client = FakeSpotifyClient(
        artists={"a1": artist_payload("a1", genres=["techno"])},  # a2 unknown
    )
    provider = ArtistGenreProvider(ArtistRepository(client, limits=settings.batch_limits))

    provider.prime(["a1", "a2"])
    # Repeated access must not trigger another fetch (a2 cached as empty).
    assert provider.genres_for("a1") == ("techno",)
    assert provider.genres_for("a2") == ()
    assert client.calls_of("artists") == [["a1", "a2"]]


def test_genre_classifier(settings: Settings) -> None:
    client = FakeSpotifyClient(artists={"a1": artist_payload("a1", genres=["deep house"])})
    provider = ArtistGenreProvider(ArtistRepository(client, limits=settings.batch_limits))
    classifier = GenreClassifier(provider, GenreTaxonomy())

    tracks = [_track("t1", "a1")]
    classifier.prepare(tracks)

    assert classifier.classify(tracks[0]) == "Electronic"
    # A track with no artist id cannot be classified.
    assert classifier.classify(_track("t2", "")) is None

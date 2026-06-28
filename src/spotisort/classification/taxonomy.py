"""Mapping of Spotify's fine-grained genres into broad buckets."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = ["DEFAULT_GENRE_RULES", "GenreRule", "GenreTaxonomy"]


@dataclass(frozen=True, slots=True)
class GenreRule:
    """A single bucket and the substrings that map a genre into it.

    Attributes:
        bucket: The broad bucket name (also used as the playlist name).
        keywords: Lower-case substrings; a genre matches if it contains any.
    """

    bucket: str
    keywords: tuple[str, ...]


#: Ordered rules; order is priority (earlier rules win). Tuned so that more
#: specific buckets are tested before broader ones (e.g. "pop punk" -> Punk,
#: "garage rock" -> Rock rather than Electronic). Override via
#: :class:`GenreTaxonomy` for different tastes.
DEFAULT_GENRE_RULES: tuple[GenreRule, ...] = (
    GenreRule("Metal", ("metal", "djent", "grindcore", "metalcore")),
    GenreRule("Punk", ("punk", "hardcore", "emo", "screamo")),
    GenreRule("Hip-Hop", ("hip hop", "hip-hop", "rap", "trap", "drill", "grime")),
    GenreRule("R&B & Soul", ("r&b", "rnb", "soul", "funk", "motown")),
    GenreRule("Reggae", ("reggae", "dancehall", "ska", "dub")),
    GenreRule("Latin", ("latin", "reggaeton", "salsa", "bachata", "cumbia", "samba")),
    GenreRule("Jazz", ("jazz", "bebop", "swing", "bossa")),
    GenreRule("Blues", ("blues",)),
    GenreRule("Classical", ("classical", "orchestra", "baroque", "opera", "compositional")),
    GenreRule("Ambient", ("ambient", "drone", "new age")),
    GenreRule(
        "Electronic",
        (
            "electro", "electronic", "edm", "house", "techno", "trance", "dubstep",
            "drum and bass", "dnb", "uk garage", "idm", "synth", "downtempo", "breakbeat",
        ),
    ),
    GenreRule("Country & Folk", ("country", "folk", "bluegrass", "americana", "singer-songwriter")),
    GenreRule("Indie & Alternative", ("indie", "alternative", "alt-")),
    GenreRule("Rock", ("rock", "grunge", "shoegaze", "britpop", "psychedelic")),
    GenreRule("Pop", ("pop",)),
)


class GenreTaxonomy:
    """Buckets Spotify genre strings into broad categories.

    Args:
        rules: Ordered rules to apply (priority = order). Defaults to
            :data:`DEFAULT_GENRE_RULES`.
        default: Bucket to use when a genre matches no rule. ``None`` means such
            genres are treated as unclassifiable.
    """

    def __init__(
        self,
        rules: Sequence[GenreRule] = DEFAULT_GENRE_RULES,
        *,
        default: str | None = None,
    ) -> None:
        self._rules = tuple(rules)
        self._default = default
        self._priority = {rule.bucket: index for index, rule in enumerate(self._rules)}

    def bucket(self, genre: str) -> str | None:
        """Return the broad bucket for a single genre string."""
        needle = genre.casefold()
        for rule in self._rules:
            if any(keyword in needle for keyword in rule.keywords):
                return rule.bucket
        return self._default

    def bucket_for(self, genres: Iterable[str]) -> str | None:
        """Return the best bucket across several genres (majority vote).

        Ties are broken by rule priority. Returns the configured default when no
        genre maps to a bucket.
        """
        counts: dict[str, int] = {}
        for genre in genres:
            bucket = self.bucket(genre)
            if bucket is not None:
                counts[bucket] = counts.get(bucket, 0) + 1
        if not counts:
            return self._default
        return min(
            counts,
            key=lambda bucket: (-counts[bucket], self._priority.get(bucket, len(self._priority))),
        )

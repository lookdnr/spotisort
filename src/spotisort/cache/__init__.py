"""Persistent SQLite cache layer.

Stores the results of the expensive reads — the full liked-songs library and
artist genres — so they survive between runs. The cache is an implementation
detail behind the repository layer; nothing above the repositories is aware of
it.
"""

from __future__ import annotations

from spotisort.cache.artist_cache import ArtistGenreCache
from spotisort.cache.database import SCHEMA_VERSION, Database
from spotisort.cache.library_cache import LibraryCache

__all__ = ["SCHEMA_VERSION", "ArtistGenreCache", "Database", "LibraryCache"]

"""Spotisort — a long-term, production-grade Spotify library organiser.

The package is organised in layers, each depending only on the one below it:

* :mod:`spotisort.api` — the thin Spotify communication layer (the only place
  raw API payloads exist).
* :mod:`spotisort.models` — pure domain dataclasses with no Spotify knowledge.
* :mod:`spotisort.mapping` — converts raw API payloads into domain models.
* :mod:`spotisort.repositories` — fetching, pagination and batching mechanics.
* :mod:`spotisort.services` — business logic (library, playlists, organising).
* :mod:`spotisort.cli` — the command-line interface.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"

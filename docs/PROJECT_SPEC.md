# Spotisort — Project Specification

> This file captures the original brief for the project. It is the source of truth
> for intent and scope. Keep it in sync if requirements change.

## Summary

A **long-term, production-grade** Python project for managing a Spotify library via the
Spotify Web API. Not a one-off script — it will keep evolving with new features for months.
Build it like a senior software engineer would.

## Priorities

- Clean architecture
- Object-oriented design
- Extensibility
- Maintainability
- Readability
- Comprehensive type hints
- Good documentation

## Technology

- Python 3.12+
- Spotipy
- python-dotenv
- pathlib
- dataclasses
- logging
- pytest-compatible project layout

Use modern Python throughout.

## Design philosophy

- Follow SOLID principles where appropriate.
- Avoid giant files.
- Avoid utility functions that should really be methods.
- Keep responsibilities separated.
- The Spotify API must only be interacted with through dedicated classes.
- Avoid leaking raw JSON outside the API layer.
- Convert Spotify responses into Python objects immediately.
- The rest of the application must never access nested dictionaries returned by Spotipy.

### Layering (thin API layer)

```
Spotify API
   -> SpotifyClient            (auth + thin API communication)
   -> Repository layer         (fetch + map + pagination/batching)
   -> Domain models            (Track, Playlist, Artist, Album)
   -> Business logic           (rules, organisation, archiving)
   -> CLI
```

Rationale: keep the API layer very thin so we can later cache in SQLite, swap Spotipy for
direct HTTP, build a web UI (Flask/FastAPI), or package as a reusable library — and so
business logic is unit-testable without talking to Spotify.

## Core classes

- `SpotifyClient` — responsible **only** for authentication and API communication.
- `SpotifyLibrary` — represents liked songs.
- `PlaylistManager` — manages playlists.

## Models (dataclasses)

`Track`, `Artist`, `Album`, `Playlist` (and supporting types such as a saved-track wrapper
carrying `added_at`).

## SpotifyLibrary behaviour

- `refresh()`
- `all_tracks()`
- `before(date)`
- `after(date)`
- `by_artist(...)`
- `by_album(...)`
- `by_year(...)`
- `search(...)`
- Handle pagination automatically.
- Cache results until `refresh()` is called.

## PlaylistManager behaviour

- `create()`
- `get()`
- `get_or_create()`
- `rename()`
- `delete()`
- `add_tracks()`
- `remove_tracks()`
- `replace_tracks()`
- Automatically batch API requests according to Spotify limits.

## Liked Songs operations

- `copy_to_playlist()`
- `move_to_playlist()`
- `like()`
- `unlike()`

**Move** must: add to playlist -> verify success -> remove from liked songs.

## Error handling

- Custom exceptions.
- Handle: expired authentication, rate limiting, API failures, missing playlists,
  missing tracks.
- Use retries where appropriate.

## Logging

- Use the `logging` module.
- Avoid `print()` except inside the CLI.

## Future expansion (DO NOT implement yet)

Architecture must accommodate without rewrites:
genre classification, mood classification, SQLite cache, duplicate detection,
smart playlists, recommendation engine, playlist synchronisation.

## Development workflow (strict)

1. Propose the architecture.
2. Explain design decisions.
3. Wait for approval.
4. Generate one file at a time.
5. Wait for approval before generating the next file.

- Never skip files.
- Never omit code.
- Never use placeholders like "implementation omitted".
- Generate production-quality code only.

## Agreed architecture (approved 2026-06-28)

`src/` layout, import package named **`spotisort`**. `pyproject.toml` + `requirements.txt`.
Mapping lives in `mapping/` (not on models). Repositories own pagination/batching;
services own caching/filtering/orchestration. `copy/move` live in a coordinating
`LibraryOrganiser` service to avoid circular deps. `print()` only in `cli/`.

### Generation order

1. `pyproject.toml` + `requirements.txt` + `.env.example`
2. `config.py`
3. `api/exceptions.py`
4. `api/client.py`
5. `models/*` (artist -> album -> track -> playlist)
6. `mapping/mappers.py`
7. `repositories/liked_songs.py`
8. `repositories/playlists.py`
9. `services/library.py`
10. `services/playlists.py`
11. `services/operations.py`
12. `cli/app.py` + `__main__.py`
13. `tests/`

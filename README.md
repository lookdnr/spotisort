# Spotisort

A long-term, production-grade tool for organising your Spotify library and
playlists from the command line, built on the Spotify Web API.

Spotisort is structured in clean, testable layers so it can keep growing —
toward genre/mood classification, a SQLite cache, duplicate detection, smart
playlists, and playlist synchronisation — without rewrites.

## Features

- Browse your liked songs with filters: by date added, artist, album, year, or
  free-text search (filters combine with logical AND).
- List, show, create, rename and delete playlists.
- **Copy** matching liked songs into a playlist.
- **Move** matching liked songs into a playlist — which adds them, verifies they
  landed, and only then removes them from Liked Songs (so nothing is lost on a
  partial failure).

## Architecture

Each layer depends only on the layer beneath it:

```
Spotify Web API
   -> api/         SpotifyClient: auth + thin, resilient API calls (retries,
                   rate-limit handling). The only place raw JSON exists.
   -> mapping/     Converts raw payloads into domain models.
   -> models/      Pure, immutable dataclasses (Artist, Album, Track,
                   SavedTrack, Playlist). No Spotify knowledge.
   -> repositories/ Pagination + batching; returns models, not payloads.
   -> services/    Business logic: SpotifyLibrary, PlaylistManager,
                   LibraryOrganiser (copy/move).
   -> cli/         The command-line interface (the only place that prints).
```

Because business logic depends on repository interfaces rather than the live
API, it is fully unit-testable with in-memory fakes — no network required.

## Requirements

- Python 3.12+
- A Spotify account and a registered app
  ([developer dashboard](https://developer.spotify.com/dashboard))

## Installation

```bash
python -m venv .venv
source .venv/bin/activate

# Runtime only:
pip install -r requirements.txt

# Or install the package (adds the `spotisort` command) with dev tools:
pip install -e ".[dev]"
```

## Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

| Variable                     | Required | Description                                        |
| ---------------------------- | -------- | -------------------------------------------------- |
| `SPOTIFY_CLIENT_ID`          | yes      | Client ID from your Spotify app.                   |
| `SPOTIFY_CLIENT_SECRET`      | yes      | Client secret from your Spotify app.               |
| `SPOTIFY_REDIRECT_URI`       | yes      | Must match a Redirect URI registered on the app.   |
| `SPOTISORT_TOKEN_CACHE_PATH` | no       | Where to cache the OAuth token.                    |
| `SPOTISORT_LOG_LEVEL`        | no       | Logging level (default `INFO`).                    |

Add the same redirect URI (e.g. `http://127.0.0.1:8888/callback`) to your app's
settings in the Spotify dashboard. The first run opens a browser to authorise
access; the token is then cached for subsequent runs.

## Usage

Run via the installed command or the module:

```bash
spotisort --help
python -m spotisort --help
```

Examples:

```bash
# List liked songs from 2001 by a given artist
spotisort liked --year 2001 --artist "Aphex Twin"

# List liked songs added before a date, limited to 20
spotisort liked --before 2020-01-01 --limit 20

# List and inspect playlists
spotisort playlists
spotisort show "My Playlist"

# Create / rename / delete
spotisort create "Focus" --description "Deep work"
spotisort rename "Focus" "Deep Focus"
spotisort delete "Deep Focus"

# Copy matching liked songs into a playlist (created if missing)
spotisort copy --to "2001 Favourites" --year 2001

# Move matching liked songs into a playlist (removes them from Liked Songs)
spotisort move --to "Archive" --before 2019-01-01

# Remove matching songs from Liked Songs (e.g. clear out old saves)
spotisort unlike --before 2020-01-01

# Group liked songs into playlists by broad genre, removing them from Liked Songs
spotisort group-genre --before 2023-01-01

# ...or keep them in Liked Songs and just copy, with a name prefix
spotisort group-genre --artist "Miles Davis" --keep --prefix "Genre: "
```

`delete`, `move`, `unlike` and `group-genre` prompt for confirmation; pass
`-y`/`--yes` to skip it. `unlike` refuses to run without at least one filter (so
it can't wipe your whole library by accident). Use `-v`/`--verbose` for debug
logging.

### Grouping by genre (and mood, later)

`group-genre` reads each track's primary-artist genres from Spotify, maps them to
broad buckets (Rock, Electronic, Hip-Hop, Jazz…), and routes each bucket into its
own playlist. Tracks whose artist has no recognised genre are reported and left
in Liked Songs untouched. Removal goes through the same add → verify → unlike
path as `move`, so nothing is lost if a step fails.

Classification sits behind a `TrackClassifier` interface, so a **mood** classifier
can be added later without changing the grouping logic. Note that Spotify
deprecated the audio-features endpoint for new apps in November 2024, so a future
mood feature would derive mood from genre, an LLM, or user-defined rules rather
than valence/energy.

## Development

```bash
pip install -e ".[dev]"

pytest         # run the test suite
ruff check .   # lint
mypy           # type-check (strict)
```

The codebase uses comprehensive type hints and is checked under `mypy --strict`.

## License

MIT

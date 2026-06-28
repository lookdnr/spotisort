"""Command-line interface for spotisort.

This module is the application's composition root and its only presentation
layer. It is therefore the one place where :func:`print`/:func:`input` are used;
every other layer communicates through return values, models and logging.

The :class:`Application` container wires the layers together lazily, and a set of
small command handlers translate parsed arguments into service calls and human
output.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from functools import cached_property

from spotisort.api.client import SpotifyClient
from spotisort.api.exceptions import SpotisortError
from spotisort.classification import ArtistGenreProvider, GenreClassifier, GenreTaxonomy
from spotisort.config import ConfigurationError, Settings
from spotisort.mapping import SpotifyMapper
from spotisort.models import Playlist, SavedTrack
from spotisort.repositories import (
    ArtistRepository,
    LikedSongsRepository,
    PlaylistRepository,
)
from spotisort.services import (
    LibraryGrouper,
    LibraryOrganiser,
    PlaylistManager,
    SpotifyLibrary,
)

logger = logging.getLogger("spotisort")

__all__ = ["Application", "build_parser", "main"]


# --------------------------------------------------------------------------- #
# Composition root
# --------------------------------------------------------------------------- #


class Application:
    """Lazily constructs and wires the application's layers from settings.

    Each component is built on first use and cached, so a command only pays for
    the parts of the stack it actually touches.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def client(self) -> SpotifyClient:
        return SpotifyClient(self.settings)

    @cached_property
    def mapper(self) -> SpotifyMapper:
        return SpotifyMapper()

    @cached_property
    def liked_repository(self) -> LikedSongsRepository:
        return LikedSongsRepository(self.client, self.mapper, limits=self.settings.batch_limits)

    @cached_property
    def playlist_repository(self) -> PlaylistRepository:
        return PlaylistRepository(self.client, self.mapper, limits=self.settings.batch_limits)

    @cached_property
    def artist_repository(self) -> ArtistRepository:
        return ArtistRepository(self.client, self.mapper, limits=self.settings.batch_limits)

    @cached_property
    def library(self) -> SpotifyLibrary:
        return SpotifyLibrary(self.liked_repository)

    @cached_property
    def playlists(self) -> PlaylistManager:
        return PlaylistManager(self.playlist_repository)

    @cached_property
    def organiser(self) -> LibraryOrganiser:
        return LibraryOrganiser(self.library, self.playlists)

    @cached_property
    def genre_classifier(self) -> GenreClassifier:
        return GenreClassifier(ArtistGenreProvider(self.artist_repository), GenreTaxonomy())

    @cached_property
    def grouper(self) -> LibraryGrouper:
        return LibraryGrouper(self.playlists, self.organiser)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    _configure_logging(settings, verbose=args.verbose)
    app = Application(settings)

    try:
        exit_code: int = args.handler(app, args)
        return exit_code
    except SpotisortError as exc:
        logger.debug("Command failed.", exc_info=True)
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("Aborted.", file=sys.stderr)
        return 130


def _configure_logging(settings: Settings, *, verbose: bool) -> None:
    level = logging.DEBUG if verbose else settings.log_level_value
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="spotisort",
        description="Organise your Spotify library and playlists.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    _add_liked_command(subparsers)
    _add_playlists_command(subparsers)
    _add_show_command(subparsers)
    _add_create_command(subparsers)
    _add_rename_command(subparsers)
    _add_delete_command(subparsers)
    _add_copy_command(subparsers)
    _add_move_command(subparsers)
    _add_unlike_command(subparsers)
    _add_group_genre_command(subparsers)

    return parser


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared liked-song selection filters to a subparser."""
    parser.add_argument("--before", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="only tracks added before this date.")
    parser.add_argument("--after", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="only tracks added after this date.")
    parser.add_argument("--artist", help="only tracks by this artist (exact, case-insensitive).")
    parser.add_argument("--album", help="only tracks on this album (exact, case-insensitive).")
    parser.add_argument("--year", type=int, help="only tracks whose album released in this year.")
    parser.add_argument("--search", help="only tracks matching this text (title/artist/album).")


def _add_liked_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("liked", help="list liked songs (optionally filtered).")
    _add_filter_arguments(parser)
    parser.add_argument("--limit", type=int, help="show at most this many tracks.")
    parser.set_defaults(handler=cmd_liked)


def _add_playlists_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("playlists", help="list your playlists.")
    parser.set_defaults(handler=cmd_playlists)


def _add_show_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("show", help="show a playlist and its tracks.")
    parser.add_argument("playlist", help="playlist name or id.")
    parser.set_defaults(handler=cmd_show)


def _add_create_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("create", help="create a new playlist.")
    parser.add_argument("name", help="name for the new playlist.")
    parser.add_argument("--public", action="store_true", help="make the playlist public.")
    parser.add_argument("--collaborative", action="store_true", help="make it collaborative.")
    parser.add_argument("--description", help="playlist description.")
    parser.set_defaults(handler=cmd_create)


def _add_rename_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("rename", help="rename a playlist.")
    parser.add_argument("playlist", help="playlist name or id.")
    parser.add_argument("new_name", help="the new name.")
    parser.set_defaults(handler=cmd_rename)


def _add_delete_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("delete", help="delete (unfollow) a playlist.")
    parser.add_argument("playlist", help="playlist name or id.")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt.")
    parser.set_defaults(handler=cmd_delete)


def _add_copy_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("copy", help="copy matching liked songs into a playlist.")
    parser.add_argument("--to", required=True, metavar="PLAYLIST",
                        help="destination playlist name (created if missing).")
    _add_filter_arguments(parser)
    parser.set_defaults(handler=cmd_copy)


def _add_move_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "move", help="move matching liked songs into a playlist (removes them from Liked Songs)."
    )
    parser.add_argument("--to", required=True, metavar="PLAYLIST",
                        help="destination playlist name (created if missing).")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt.")
    _add_filter_arguments(parser)
    parser.set_defaults(handler=cmd_move)


def _add_unlike_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "unlike", help="remove matching songs from Liked Songs (e.g. everything before a date)."
    )
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt.")
    _add_filter_arguments(parser)
    parser.set_defaults(handler=cmd_unlike)


def _add_group_genre_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "group-genre",
        help="group matching liked songs into playlists by broad genre (removes them by default).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="copy into playlists instead of removing from Liked Songs.",
    )
    parser.add_argument(
        "--prefix", default="", help="text to prepend to each genre playlist name (e.g. 'Genre: ')."
    )
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt.")
    _add_filter_arguments(parser)
    parser.set_defaults(handler=cmd_group_genre)


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #


def cmd_liked(app: Application, args: argparse.Namespace) -> int:
    selected = _select_saved(app.library, args)
    if args.limit is not None:
        selected = selected[: max(args.limit, 0)]
    for saved in selected:
        print(_format_saved(saved))
    print(f"\n{len(selected)} track(s).")
    return 0


def cmd_playlists(app: Application, args: argparse.Namespace) -> int:
    playlists = app.playlists.all_playlists()
    for playlist in playlists:
        print(f"{playlist.id}  {playlist.name}  ({playlist.track_count} tracks)")
    print(f"\n{len(playlists)} playlist(s).")
    return 0


def cmd_show(app: Application, args: argparse.Namespace) -> int:
    playlist = _resolve_playlist(app, args.playlist, with_tracks=True)
    print(f"{playlist.name}  ({playlist.track_count} tracks)")
    if playlist.description:
        print(playlist.description)
    print()
    for index, track in enumerate(playlist.tracks or (), start=1):
        print(f"{index:>4}. {track.display_name()}")
    return 0


def cmd_create(app: Application, args: argparse.Namespace) -> int:
    playlist = app.playlists.create(
        args.name,
        public=args.public,
        collaborative=args.collaborative,
        description=args.description,
    )
    print(f"Created playlist {playlist.name!r} ({playlist.id}).")
    return 0


def cmd_rename(app: Application, args: argparse.Namespace) -> int:
    playlist = _resolve_playlist(app, args.playlist)
    updated = app.playlists.rename(playlist, args.new_name)
    print(f"Renamed to {updated.name!r}.")
    return 0


def cmd_delete(app: Application, args: argparse.Namespace) -> int:
    playlist = _resolve_playlist(app, args.playlist)
    if not _confirm(f"Delete playlist {playlist.name!r}?", assume_yes=args.yes):
        print("Cancelled.")
        return 0
    app.playlists.delete(playlist)
    print(f"Deleted playlist {playlist.name!r}.")
    return 0


def cmd_copy(app: Application, args: argparse.Namespace) -> int:
    selected = _select_saved(app.library, args)
    if not selected:
        print("No matching liked songs.")
        return 0
    playlist = app.playlists.get_or_create(args.to)
    count = app.organiser.copy_to_playlist(selected, playlist)
    print(f"Copied {count} track(s) into {playlist.name!r}.")
    return 0


def cmd_move(app: Application, args: argparse.Namespace) -> int:
    selected = _select_saved(app.library, args)
    if not selected:
        print("No matching liked songs.")
        return 0
    prompt = f"Move {len(selected)} track(s) into {args.to!r} and remove them from Liked Songs?"
    if not _confirm(prompt, assume_yes=args.yes):
        print("Cancelled.")
        return 0
    playlist = app.playlists.get_or_create(args.to)
    result = app.organiser.move_to_playlist(selected, playlist)
    print(
        f"Moved {result.added} track(s) into {result.playlist.name!r}; "
        f"removed {result.removed} from Liked Songs."
    )
    return 0


def cmd_unlike(app: Application, args: argparse.Namespace) -> int:
    # Guard against accidentally clearing the whole library with a bare `unlike`.
    if not _has_any_filter(args):
        print(
            "Refusing to unlike your entire library. Pass at least one filter, "
            "e.g. --before 2020-01-01.",
            file=sys.stderr,
        )
        return 2
    selected = _select_saved(app.library, args)
    if not selected:
        print("No matching liked songs.")
        return 0
    prompt = f"Remove {len(selected)} track(s) from Liked Songs? This cannot be undone."
    if not _confirm(prompt, assume_yes=args.yes):
        print("Cancelled.")
        return 0
    removed = app.library.unlike(selected)
    print(f"Removed {removed} track(s) from Liked Songs.")
    return 0


def cmd_group_genre(app: Application, args: argparse.Namespace) -> int:
    selected = _select_saved(app.library, args)
    if not selected:
        print("No matching liked songs.")
        return 0

    remove = not args.keep
    if remove:
        prompt = (
            f"Group {len(selected)} track(s) by genre into playlists and "
            "remove them from Liked Songs?"
        )
        if not _confirm(prompt, assume_yes=args.yes):
            print("Cancelled.")
            return 0

    name_template = f"{args.prefix}{{category}}" if args.prefix else "{category}"
    result = app.grouper.group(
        selected,
        app.genre_classifier,
        remove_from_library=remove,
        name_template=name_template,
    )

    for outcome in result.groups:
        if remove:
            print(
                f"{outcome.playlist.name}: +{outcome.added} added, "
                f"-{outcome.removed} from Liked Songs."
            )
        else:
            print(f"{outcome.playlist.name}: +{outcome.added} added.")
    if not result.groups:
        print("Nothing could be classified by genre.")
    if result.unclassified:
        print(
            f"{len(result.unclassified)} track(s) had no recognised genre "
            "and were left in Liked Songs."
        )
    return 0


# --------------------------------------------------------------------------- #
# Handler helpers
# --------------------------------------------------------------------------- #


def _has_any_filter(args: argparse.Namespace) -> bool:
    """Whether at least one liked-song selection filter was supplied."""
    return any(
        getattr(args, name, None) is not None
        for name in ("before", "after", "artist", "album", "year", "search")
    )


def _select_saved(library: SpotifyLibrary, args: argparse.Namespace) -> list[SavedTrack]:
    """Apply whichever filters were supplied, combined with logical AND.

    Each filter narrows the running result set by intersection, preserving the
    library's original ordering.
    """
    results = library.all_tracks()

    def narrow(subset: list[SavedTrack]) -> list[SavedTrack]:
        allowed = set(subset)
        return [saved for saved in results if saved in allowed]

    if args.before is not None:
        results = narrow(library.before(args.before))
    if args.after is not None:
        results = narrow(library.after(args.after))
    if args.artist:
        results = narrow(library.by_artist(args.artist))
    if args.album:
        results = narrow(library.by_album(args.album))
    if args.year is not None:
        results = narrow(library.by_year(args.year))
    if args.search:
        results = narrow(library.search(args.search))

    return results


def _resolve_playlist(app: Application, reference: str, *, with_tracks: bool = False) -> Playlist:
    """Resolve a playlist by name first, falling back to treating it as an id."""
    found = app.playlists.find_by_name(reference)
    if found is not None:
        return app.playlists.get(found, with_tracks=with_tracks) if with_tracks else found
    return app.playlists.get(reference, with_tracks=with_tracks)


def _format_saved(saved: SavedTrack) -> str:
    """Format a saved track as a single display line."""
    year = saved.track.release_year
    suffix = f"  ({year})" if year else ""
    return f"{saved.added_at.date()}  {saved.track.display_name()}{suffix}"


def _confirm(prompt: str, *, assume_yes: bool) -> bool:
    """Ask the user to confirm a destructive action, unless pre-approved."""
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}

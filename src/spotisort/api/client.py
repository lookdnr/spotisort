"""The Spotify client — authentication and raw API communication.

:class:`SpotifyClient` is the single seam between spotisort and Spotipy. Its
responsibilities are deliberately narrow:

* build and own the OAuth session;
* expose thin, named pass-through methods for the endpoints spotisort uses;
* centralise retry/backoff and rate-limit handling in one place;
* translate Spotipy's exceptions into spotisort's exception hierarchy.

Everything it returns is a raw payload (``dict``/``list``). Converting those into
domain models is the job of :mod:`spotisort.mapping`; the client never imports a
model. Batching of large request payloads is the job of the repository layer;
the client passes through whatever it is given.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import spotipy
from requests.exceptions import RequestException
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

from spotisort.api.exceptions import (
    AuthenticationError,
    RateLimitError,
    RequestFailedError,
    RetriesExhaustedError,
)
from spotisort.config import RetryPolicy, Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: HTTP statuses that represent transient server-side failures worth retrying.
_RETRYABLE_STATUSES: frozenset[int] = frozenset({500, 502, 503, 504})


class SpotifyClient:
    """A thin, resilient wrapper around :class:`spotipy.Spotify`.

    Args:
        settings: Validated application configuration.
        client: An existing Spotipy client to use instead of building one.
            Primarily a testing seam — pass a fake to avoid any network or auth.
        auth_manager: An OAuth manager to use when building the Spotipy client.
            Ignored when ``client`` is supplied. Defaults to a
            :class:`spotipy.oauth2.SpotifyOAuth` built from ``settings``.
        sleeper: Callable used to wait between retries. Injectable so tests can
            avoid real delays. Defaults to :func:`time.sleep`.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: spotipy.Spotify | None = None,
        auth_manager: SpotifyOAuth | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._retry: RetryPolicy = settings.retry
        self._sleep = sleeper
        self._auth_manager = auth_manager
        self._client = client or self._build_client(settings, auth_manager)
        self._user_id: str | None = None

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_client(
        settings: Settings,
        auth_manager: SpotifyOAuth | None,
    ) -> spotipy.Spotify:
        """Build a Spotipy client with an OAuth manager derived from settings."""
        manager = auth_manager or SpotifyOAuth(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            redirect_uri=settings.redirect_uri,
            scope=settings.scope_string(),
            cache_handler=CacheFileHandler(cache_path=str(settings.token_cache_path)),
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=manager)

    # ------------------------------------------------------------------ #
    # User
    # ------------------------------------------------------------------ #

    def current_user(self) -> dict[str, Any]:
        """Return the raw profile of the authenticated user."""
        return self._call(self._client.current_user, operation="fetch current user")

    def current_user_id(self) -> str:
        """Return the authenticated user's id, fetching and caching it once.

        The id is required to create playlists; caching avoids repeating the
        profile request for every operation within a session.
        """
        if self._user_id is None:
            profile = self.current_user()
            user_id = profile.get("id")
            if not user_id:
                raise RequestFailedError("Spotify did not return a user id for the current user.")
            self._user_id = str(user_id)
        return self._user_id

    # ------------------------------------------------------------------ #
    # Artists
    # ------------------------------------------------------------------ #

    def artists(self, artist_ids: Sequence[str]) -> dict[str, Any]:
        """Return full artist objects for a single batch of ids (max 50)."""
        return self._call(
            self._client.artists,
            list(artist_ids),
            operation="fetch artists",
        )

    # ------------------------------------------------------------------ #
    # Liked songs (the user's saved tracks)
    # ------------------------------------------------------------------ #

    def saved_tracks(self, *, limit: int, offset: int) -> dict[str, Any]:
        """Return one raw page of the user's saved (liked) tracks."""
        return self._call(
            self._client.current_user_saved_tracks,
            limit=limit,
            offset=offset,
            operation="fetch saved tracks",
        )

    def saved_tracks_contains(self, track_ids: Sequence[str]) -> list[bool]:
        """Return, per id, whether the track is in the user's library."""
        return self._call(
            self._client.current_user_saved_tracks_contains,
            tracks=list(track_ids),
            operation="check saved tracks",
        )

    def saved_tracks_add(self, track_ids: Sequence[str]) -> None:
        """Add the given tracks to the user's library (one batch)."""
        self._call(
            self._client.current_user_saved_tracks_add,
            tracks=list(track_ids),
            operation="add saved tracks",
        )

    def saved_tracks_delete(self, track_ids: Sequence[str]) -> None:
        """Remove the given tracks from the user's library (one batch)."""
        self._call(
            self._client.current_user_saved_tracks_delete,
            tracks=list(track_ids),
            operation="remove saved tracks",
        )

    # ------------------------------------------------------------------ #
    # Playlists
    # ------------------------------------------------------------------ #

    def current_user_playlists(self, *, limit: int, offset: int) -> dict[str, Any]:
        """Return one raw page of the current user's playlists."""
        return self._call(
            self._client.current_user_playlists,
            limit=limit,
            offset=offset,
            operation="fetch user playlists",
        )

    def playlist(self, playlist_id: str, *, fields: str | None = None) -> dict[str, Any]:
        """Return a raw playlist object, optionally restricted to ``fields``."""
        return self._call(
            self._client.playlist,
            playlist_id,
            fields=fields,
            operation="fetch playlist",
        )

    def playlist_items(
        self,
        playlist_id: str,
        *,
        limit: int,
        offset: int,
        fields: str | None = None,
    ) -> dict[str, Any]:
        """Return one raw page of a playlist's items (tracks only)."""
        return self._call(
            self._client.playlist_items,
            playlist_id,
            limit=limit,
            offset=offset,
            fields=fields,
            additional_types=("track",),
            operation="fetch playlist items",
        )

    def create_playlist(
        self,
        *,
        user_id: str,
        name: str,
        public: bool,
        collaborative: bool,
        description: str | None,
    ) -> dict[str, Any]:
        """Create a playlist for ``user_id`` and return the raw playlist object."""
        return self._call(
            self._client.user_playlist_create,
            user_id,
            name,
            public=public,
            collaborative=collaborative,
            description=description or "",
            operation="create playlist",
        )

    def change_playlist_details(
        self,
        playlist_id: str,
        *,
        name: str | None = None,
        public: bool | None = None,
        collaborative: bool | None = None,
        description: str | None = None,
    ) -> None:
        """Change one or more mutable attributes of a playlist.

        Only the attributes that are not ``None`` are sent. At least one must be
        provided.
        """
        changes: dict[str, Any] = {
            key: value
            for key, value in (
                ("name", name),
                ("public", public),
                ("collaborative", collaborative),
                ("description", description),
            )
            if value is not None
        }
        if not changes:
            raise ValueError("change_playlist_details requires at least one attribute to change.")
        self._call(
            self._client.playlist_change_details,
            playlist_id,
            operation="change playlist details",
            **changes,
        )

    def playlist_add_items(
        self,
        playlist_id: str,
        track_uris: Sequence[str],
        *,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Add a single batch of track URIs to a playlist."""
        return self._call(
            self._client.playlist_add_items,
            playlist_id,
            list(track_uris),
            position=position,
            operation="add items to playlist",
        )

    def playlist_remove_items(
        self,
        playlist_id: str,
        track_uris: Sequence[str],
    ) -> dict[str, Any]:
        """Remove all occurrences of a single batch of track URIs from a playlist."""
        return self._call(
            self._client.playlist_remove_all_occurrences_of_items,
            playlist_id,
            list(track_uris),
            operation="remove items from playlist",
        )

    def playlist_replace_items(
        self,
        playlist_id: str,
        track_uris: Sequence[str],
    ) -> dict[str, Any]:
        """Replace a playlist's items with a single batch of track URIs.

        Spotify's replace endpoint accepts at most one full batch; replacing a
        longer list (add-after-clear) is orchestrated by the repository layer.
        """
        return self._call(
            self._client.playlist_replace_items,
            playlist_id,
            list(track_uris),
            operation="replace playlist items",
        )

    def unfollow_playlist(self, playlist_id: str) -> None:
        """Unfollow (the Spotify equivalent of "delete") the given playlist."""
        self._call(
            self._client.current_user_unfollow_playlist,
            playlist_id,
            operation="unfollow playlist",
        )

    # ------------------------------------------------------------------ #
    # Core call / retry machinery
    # ------------------------------------------------------------------ #

    def _call(self, func: Callable[..., T], *args: Any, operation: str, **kwargs: Any) -> T:
        """Invoke a Spotipy call with retries, backoff and error translation.

        Args:
            func: The bound Spotipy method to call.
            *args: Positional arguments forwarded to ``func``.
            operation: Human-readable label for the operation, used in logs and
                error messages. Named ``operation`` (not ``description``) to
                avoid colliding with Spotify's own ``description`` keyword on the
                playlist endpoints.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever ``func`` returns (a raw API payload).

        Raises:
            AuthenticationError: On an unrecoverable ``401``.
            RateLimitError: On a ``429`` after retries are exhausted.
            RetriesExhaustedError: On transient server/network errors after
                retries are exhausted.
            RequestFailedError: On a non-retryable API error.
        """
        attempts = self._retry.max_attempts
        last_error: BaseException | None = None

        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except spotipy.SpotifyException as exc:
                last_error = exc
                status = exc.http_status
                reason = getattr(exc, "reason", None)

                if status == 401:
                    raise AuthenticationError(
                        f"Authentication failed during {operation}.",
                        reason=reason,
                    ) from exc

                if status == 429:
                    if attempt >= attempts:
                        retry_after = self._retry_after_seconds(exc)
                        raise RateLimitError(
                            f"Rate limited during {operation}; retries exhausted.",
                            retry_after=retry_after,
                            reason=reason,
                        ) from exc
                    self._wait_after_rate_limit(exc, attempt, operation)
                    continue

                if status in _RETRYABLE_STATUSES:
                    if attempt >= attempts:
                        break
                    self._wait_with_backoff(attempt, operation, reason=f"HTTP {status}")
                    continue

                # Any other 4xx is a caller/permanent error: do not retry.
                raise RequestFailedError(
                    f"Spotify request failed during {operation}.",
                    http_status=status,
                    reason=reason,
                ) from exc

            except RequestException as exc:
                # Transport-level failure (timeout, connection reset, ...).
                last_error = exc
                if attempt >= attempts:
                    break
                self._wait_with_backoff(attempt, operation, reason=type(exc).__name__)
                continue

        raise RetriesExhaustedError(
            f"Spotify request failed during {operation} after {attempts} attempt(s).",
            attempts=attempts,
            last_error=last_error,
        ) from last_error

    def _wait_after_rate_limit(
        self,
        exc: spotipy.SpotifyException,
        attempt: int,
        operation: str,
    ) -> None:
        """Sleep in response to a ``429``, honouring ``Retry-After`` when present."""
        retry_after = self._retry_after_seconds(exc)
        if retry_after is not None and self._retry.respect_retry_after:
            delay = retry_after
        else:
            delay = self._retry.backoff_for(attempt)
        logger.warning(
            "Rate limited during %s; waiting %.1fs before retry (attempt %d/%d).",
            operation,
            delay,
            attempt,
            self._retry.max_attempts,
        )
        self._sleep(delay)

    def _wait_with_backoff(self, attempt: int, operation: str, *, reason: str) -> None:
        """Sleep for the policy's exponential backoff before the next attempt."""
        delay = self._retry.backoff_for(attempt)
        logger.warning(
            "Transient failure (%s) during %s; retrying in %.1fs (attempt %d/%d).",
            reason,
            operation,
            delay,
            attempt,
            self._retry.max_attempts,
        )
        self._sleep(delay)

    @staticmethod
    def _retry_after_seconds(exc: spotipy.SpotifyException) -> float | None:
        """Extract a ``Retry-After`` value (seconds) from a Spotipy exception."""
        headers = getattr(exc, "headers", None)
        if not headers:
            return None
        raw = headers.get("Retry-After") or headers.get("retry-after")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

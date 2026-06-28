"""Exception hierarchy for spotisort.

All application errors derive from :class:`SpotisortError`, giving callers a
single base class to catch. Errors that originate from talking to Spotify derive
from :class:`SpotifyApiError`, which carries the HTTP status and Spotify's
``reason`` code where available.

The translation from Spotipy's :class:`spotipy.SpotifyException` into these
types lives in the client (:mod:`spotisort.api.client`), so this module stays
free of any third-party imports and can be depended upon by every layer.
"""

from __future__ import annotations

__all__ = [
    "AuthenticationError",
    "MappingError",
    "PlaylistNotFoundError",
    "RateLimitError",
    "RequestFailedError",
    "ResourceNotFoundError",
    "RetriesExhaustedError",
    "SpotifyApiError",
    "SpotisortError",
    "TrackNotFoundError",
]


class SpotisortError(Exception):
    """Base class for every error raised by spotisort."""


# --------------------------------------------------------------------------- #
# Spotify API errors
# --------------------------------------------------------------------------- #


class SpotifyApiError(SpotisortError):
    """Base class for failures that occur while communicating with Spotify.

    Attributes:
        http_status: The HTTP status code returned by Spotify, if known.
        reason: Spotify's machine-readable ``reason`` string, if provided.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.reason = reason

    def __str__(self) -> str:
        base = super().__str__()
        details: list[str] = []
        if self.http_status is not None:
            details.append(f"HTTP {self.http_status}")
        if self.reason:
            details.append(f"reason={self.reason}")
        return f"{base} ({', '.join(details)})" if details else base


class AuthenticationError(SpotifyApiError):
    """Raised when authentication fails or the access token has expired.

    Typically corresponds to an HTTP ``401`` that could not be resolved by
    refreshing the token.
    """

    def __init__(
        self,
        message: str = "Spotify authentication failed or the token has expired.",
        *,
        http_status: int | None = 401,
        reason: str | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, reason=reason)


class RateLimitError(SpotifyApiError):
    """Raised when Spotify returns ``429 Too Many Requests``.

    Attributes:
        retry_after: The number of seconds Spotify asked the caller to wait,
            taken from the ``Retry-After`` header when present.
    """

    def __init__(
        self,
        message: str = "Spotify rate limit exceeded.",
        *,
        retry_after: float | None = None,
        http_status: int | None = 429,
        reason: str | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, reason=reason)
        self.retry_after = retry_after


class RequestFailedError(SpotifyApiError):
    """Raised for an API failure that is not covered by a more specific type."""


class RetriesExhaustedError(SpotifyApiError):
    """Raised when an operation still fails after exhausting all retry attempts.

    Attributes:
        attempts: How many attempts were made before giving up.
        last_error: The final underlying error that caused the operation to fail.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_error: BaseException | None = None,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, reason=reason)
        self.attempts = attempts
        self.last_error = last_error


class ResourceNotFoundError(SpotifyApiError):
    """Base class for "the thing you asked for does not exist" errors.

    Attributes:
        resource_id: The identifier (Spotify ID or URI) that could not be found.
    """

    #: Human-readable label for the resource, overridden by subclasses.
    resource_label: str = "resource"

    def __init__(
        self,
        resource_id: str,
        *,
        message: str | None = None,
        http_status: int | None = 404,
        reason: str | None = None,
    ) -> None:
        super().__init__(
            message or f"{self.resource_label.capitalize()} not found: {resource_id!r}.",
            http_status=http_status,
            reason=reason,
        )
        self.resource_id = resource_id


class PlaylistNotFoundError(ResourceNotFoundError):
    """Raised when a playlist cannot be found by id or by name."""

    resource_label = "playlist"


class TrackNotFoundError(ResourceNotFoundError):
    """Raised when a track cannot be found."""

    resource_label = "track"


# --------------------------------------------------------------------------- #
# Mapping errors
# --------------------------------------------------------------------------- #


class MappingError(SpotisortError):
    """Raised when a raw Spotify payload cannot be converted into a model.

    This indicates the payload was missing required fields or had an unexpected
    shape — i.e. a contract mismatch between spotisort and the Spotify API —
    rather than a transport failure.
    """

"""Application configuration.

This module is intentionally self-contained: it depends on nothing else inside
``spotisort`` so that it can be imported and validated *before* any part of the
Spotify API layer is constructed. For the same reason :class:`ConfigurationError`
is deliberately separate from the Spotify API exception hierarchy defined in
:mod:`spotisort.api.exceptions` — a configuration failure happens before there is
any API session to fail against.

Configuration is modelled as immutable dataclasses. The usual entry point is
:meth:`Settings.from_env`, which loads a ``.env`` file (via python-dotenv) and
builds a validated :class:`Settings` instance.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv as _load_dotenv

__all__ = [
    "REQUIRED_SCOPES",
    "BatchLimits",
    "ConfigurationError",
    "RetryPolicy",
    "Settings",
]

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_TOKEN_CACHE_PATH = Path(".cache-spotisort")
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CACHE_PATH = Path(".spotisort-cache.db")
DEFAULT_CACHE_TTL_SECONDS = 86400  # 24 hours

#: OAuth scopes required for every operation spotisort performs. Reading and
#: modifying liked songs needs the ``user-library-*`` scopes; reading and
#: modifying both private and public playlists needs the ``playlist-*`` scopes.
REQUIRED_SCOPES: tuple[str, ...] = (
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
)

# Environment variable names, declared once so they can be reused in messages.
_ENV_CLIENT_ID = "SPOTIFY_CLIENT_ID"
_ENV_CLIENT_SECRET = "SPOTIFY_CLIENT_SECRET"
_ENV_REDIRECT_URI = "SPOTIFY_REDIRECT_URI"
_ENV_TOKEN_CACHE_PATH = "SPOTISORT_TOKEN_CACHE_PATH"
_ENV_LOG_LEVEL = "SPOTISORT_LOG_LEVEL"
_ENV_CACHE_PATH = "SPOTISORT_CACHE_PATH"
_ENV_CACHE_TTL = "SPOTISORT_CACHE_TTL"
_ENV_CACHE_ENABLED = "SPOTISORT_CACHE"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


# --------------------------------------------------------------------------- #
# Policy / limit value objects
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How the API layer should retry transient failures.

    Attributes:
        max_attempts: Total number of attempts (including the first) before
            giving up. Must be at least 1.
        backoff_base_seconds: Base delay for exponential backoff. The delay for
            attempt ``n`` (1-indexed) is ``backoff_base_seconds * 2 ** (n - 1)``,
            capped at :attr:`backoff_max_seconds`.
        backoff_max_seconds: Upper bound on any single backoff delay.
        respect_retry_after: When ``True``, a ``Retry-After`` value supplied by
            Spotify on a ``429`` response takes precedence over computed backoff.
    """

    max_attempts: int = 5
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 30.0
    respect_retry_after: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigurationError("RetryPolicy.max_attempts must be at least 1.")
        if self.backoff_base_seconds < 0:
            raise ConfigurationError("RetryPolicy.backoff_base_seconds must not be negative.")
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ConfigurationError(
                "RetryPolicy.backoff_max_seconds must be >= backoff_base_seconds."
            )

    def backoff_for(self, attempt: int) -> float:
        """Return the exponential backoff delay (seconds) for a 1-indexed attempt."""
        if attempt < 1:
            raise ValueError("attempt must be 1-indexed and >= 1.")
        delay: float = self.backoff_base_seconds * (2 ** (attempt - 1))
        return min(delay, self.backoff_max_seconds)


@dataclass(frozen=True, slots=True)
class BatchLimits:
    """Page sizes and batch sizes imposed by the Spotify Web API.

    These mirror the documented maxima for each endpoint. They live in
    configuration (rather than as magic numbers in the repositories) so that the
    batching logic has a single, named source of truth that is easy to audit and
    to adjust should the API change.
    """

    #: Max ``limit`` when reading liked songs (GET /me/tracks).
    saved_tracks_page: int = 50
    #: Max ``limit`` when reading items of a playlist (GET playlist items).
    playlist_items_page: int = 100
    #: Max ``limit`` when reading the current user's playlists (GET /me/playlists).
    playlists_page: int = 50
    #: Max tracks per add/remove/replace request against a playlist.
    playlist_modify_batch: int = 100
    #: Max tracks per save/remove request against the user's library.
    library_modify_batch: int = 50
    #: Max artist ids per request when fetching full artists (GET /v1/artists).
    artists_batch: int = 50

    def __post_init__(self) -> None:
        for name in self.__slots__:
            if getattr(self, name) < 1:
                raise ConfigurationError(f"BatchLimits.{name} must be at least 1.")


# --------------------------------------------------------------------------- #
# Top-level settings
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable, validated application configuration.

    Construct directly for tests, or use :meth:`from_env` for normal runs.
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = REQUIRED_SCOPES
    token_cache_path: Path = DEFAULT_TOKEN_CACHE_PATH
    log_level: str = DEFAULT_LOG_LEVEL
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    batch_limits: BatchLimits = field(default_factory=BatchLimits)
    cache_enabled: bool = True
    cache_path: Path = DEFAULT_CACHE_PATH
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS

    def __post_init__(self) -> None:
        if not self.client_id:
            raise ConfigurationError("client_id must not be empty.")
        if not self.client_secret:
            raise ConfigurationError("client_secret must not be empty.")
        if not self.redirect_uri:
            raise ConfigurationError("redirect_uri must not be empty.")
        if not self.scopes:
            raise ConfigurationError("At least one OAuth scope is required.")
        if self.cache_ttl_seconds < 0:
            raise ConfigurationError("cache_ttl_seconds must not be negative.")

        # Coerce string paths (e.g. supplied by a test) into Paths.
        object.__setattr__(self, "token_cache_path", Path(self.token_cache_path))
        object.__setattr__(self, "cache_path", Path(self.cache_path))

        normalised_level = self.log_level.strip().upper()
        valid_levels = logging.getLevelNamesMapping()
        if normalised_level not in valid_levels:
            raise ConfigurationError(
                f"Invalid log level {self.log_level!r}. "
                f"Expected one of: {', '.join(sorted(valid_levels))}."
            )
        object.__setattr__(self, "log_level", normalised_level)

    @property
    def log_level_value(self) -> int:
        """The numeric :mod:`logging` level corresponding to :attr:`log_level`."""
        return logging.getLevelNamesMapping()[self.log_level]

    @property
    def cache_ttl(self) -> timedelta | None:
        """The liked-songs cache lifetime, or ``None`` when it never expires.

        A configured value of ``0`` means cached data is kept until it is
        explicitly refreshed or invalidated by a write.
        """
        if self.cache_ttl_seconds <= 0:
            return None
        return timedelta(seconds=self.cache_ttl_seconds)

    def scope_string(self) -> str:
        """Return the space-delimited scope string expected by the OAuth flow."""
        return " ".join(self.scopes)

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        *,
        load_dotenv: bool = True,
    ) -> Settings:
        """Build :class:`Settings` from environment variables.

        Args:
            env_file: Optional explicit path to a ``.env`` file. When ``None``
                and ``load_dotenv`` is ``True``, python-dotenv searches upward
                from the current working directory for a ``.env`` file.
            load_dotenv: When ``True`` (the default) a ``.env`` file is loaded
                into the process environment before reading values. Set to
                ``False`` to read only from the existing environment.

        Returns:
            A validated :class:`Settings` instance.

        Raises:
            ConfigurationError: If any required variable is missing or empty.
        """
        if load_dotenv:
            if env_file is not None:
                _load_dotenv(env_file)
            else:
                _load_dotenv()

        missing: list[str] = []
        client_id = _read_required(_ENV_CLIENT_ID, missing)
        client_secret = _read_required(_ENV_CLIENT_SECRET, missing)
        redirect_uri = _read_required(_ENV_REDIRECT_URI, missing)
        if missing:
            raise ConfigurationError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in your Spotify credentials."
            )

        token_cache_path = Path(
            _read_optional(_ENV_TOKEN_CACHE_PATH) or str(DEFAULT_TOKEN_CACHE_PATH)
        )
        log_level = _read_optional(_ENV_LOG_LEVEL) or DEFAULT_LOG_LEVEL
        cache_path = Path(_read_optional(_ENV_CACHE_PATH) or str(DEFAULT_CACHE_PATH))
        cache_enabled = _read_bool(_ENV_CACHE_ENABLED, default=True)
        cache_ttl_seconds = _read_int(
            _ENV_CACHE_TTL, default=DEFAULT_CACHE_TTL_SECONDS, minimum=0
        )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            token_cache_path=token_cache_path,
            log_level=log_level,
            cache_enabled=cache_enabled,
            cache_path=cache_path,
            cache_ttl_seconds=cache_ttl_seconds,
        )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _read_required(name: str, missing: list[str]) -> str:
    """Read a required env var, recording its name in ``missing`` if absent."""
    value = os.environ.get(name, "").strip()
    if not value:
        missing.append(name)
    return value


def _read_optional(name: str) -> str:
    """Read an optional env var, returning a stripped value or empty string."""
    return os.environ.get(name, "").strip()


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _read_bool(name: str, *, default: bool) -> bool:
    """Read an optional boolean env var, falling back to ``default``."""
    raw = _read_optional(name).lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ConfigurationError(
        f"Invalid boolean for {name}: {raw!r}. Use one of: "
        f"{', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}."
    )


def _read_int(name: str, *, default: int, minimum: int | None = None) -> int:
    """Read an optional integer env var, falling back to ``default``."""
    raw = _read_optional(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"Invalid integer for {name}: {raw!r}.") from exc
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}; got {value}.")
    return value

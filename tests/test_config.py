"""Tests for :mod:`spotisort.config`."""

from __future__ import annotations

import pytest

from spotisort.config import BatchLimits, ConfigurationError, RetryPolicy, Settings


def test_from_env_builds_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1/cb")
    monkeypatch.setenv("SPOTISORT_LOG_LEVEL", "debug")

    settings = Settings.from_env(load_dotenv=False)

    assert settings.client_id == "id"
    assert settings.log_level == "DEBUG"
    assert "user-library-read" in settings.scope_string()


def test_from_env_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError) as excinfo:
        Settings.from_env(load_dotenv=False)

    assert "SPOTIFY_CLIENT_ID" in str(excinfo.value)


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ConfigurationError):
        Settings(
            client_id="a",
            client_secret="b",
            redirect_uri="c",
            log_level="LOUD",
        )


def test_retry_policy_backoff_is_capped() -> None:
    policy = RetryPolicy(backoff_base_seconds=1.0, backoff_max_seconds=4.0)
    assert policy.backoff_for(1) == 1.0
    assert policy.backoff_for(2) == 2.0
    assert policy.backoff_for(10) == 4.0  # capped


def test_retry_policy_rejects_zero_attempts() -> None:
    with pytest.raises(ConfigurationError):
        RetryPolicy(max_attempts=0)


def test_batch_limits_reject_non_positive() -> None:
    with pytest.raises(ConfigurationError):
        BatchLimits(playlist_modify_batch=0)

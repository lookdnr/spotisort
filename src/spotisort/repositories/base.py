"""Shared base for repositories.

Repositories sit just above the API client. They own the *mechanical* concerns
of talking to Spotify in bulk — following pagination cursors and splitting large
payloads into API-sized batches — and they return domain models rather than raw
payloads. Higher-level policy (caching, filtering, multi-step orchestration)
belongs in the service layer, not here.

The pagination and batching helpers live on this base class (rather than as free
functions) so that every repository shares one implementation and subclasses can
call them as methods.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from spotisort.api.client import SpotifyClient
from spotisort.config import BatchLimits
from spotisort.mapping import SpotifyMapper

logger = logging.getLogger(__name__)

#: Signature of a paged-endpoint fetcher: ``fetch(limit, offset) -> page``.
PageFetcher = Callable[[int, int], Mapping[str, Any]]


class Repository:
    """Base class holding shared dependencies and bulk-request helpers.

    Args:
        client: The Spotify client used for all communication.
        mapper: The set of mappers used to convert payloads into models.
            Defaults to a freshly assembled :class:`SpotifyMapper`.
        limits: The API page/batch limits to honour. Defaults to
            :class:`BatchLimits` defaults; the composition root should pass
            ``settings.batch_limits``.
    """

    def __init__(
        self,
        client: SpotifyClient,
        mapper: SpotifyMapper | None = None,
        *,
        limits: BatchLimits | None = None,
    ) -> None:
        self._client = client
        self._mapper = mapper or SpotifyMapper()
        self._limits = limits or BatchLimits()

    @staticmethod
    def _iter_offset_items(fetch: PageFetcher, *, page_size: int) -> Iterator[Any]:
        """Yield every item across an offset-paginated endpoint.

        Args:
            fetch: Callable returning one raw page given ``(limit, offset)``.
            page_size: Number of items to request per page.

        Yields:
            Each raw item dict from the ``"items"`` array of every page, in order.
        """
        offset = 0
        while True:
            page = fetch(page_size, offset)
            items = page.get("items") or []
            yield from items
            offset += len(items)
            # Stop on a short/empty page or when Spotify reports no further page.
            if not items or len(items) < page_size or page.get("next") is None:
                break

    @staticmethod
    def _chunk(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
        """Split a sequence into consecutive chunks of at most ``size`` items."""
        if size < 1:
            raise ValueError("chunk size must be at least 1.")
        for start in range(0, len(items), size):
            yield items[start : start + size]

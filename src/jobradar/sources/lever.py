"""Lever adapter — one class for every Lever posting board.

Lever exposes a public JSON API that returns *all* postings for an account as a
single JSON array (no pagination):

    GET https://api.lever.co/v0/postings/{account}?mode=json

The account is the first path segment of the public board URL
(``https://jobs.lever.co/{account}``). Lever's ``createdAt`` is a Unix epoch in
*milliseconds*, which we convert to a timezone-aware :attr:`Job.posted_at`.
"""

from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "lever"
_API_BASE = "https://api.lever.co/v0/postings"


class LeverSource(JobSource):
    """Fetch postings from a single Lever account."""

    def __init__(
        self,
        account: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> None:
        self._account = account
        self._client = client
        self._company = company or account
        self._endpoint = f"{_API_BASE}/{account}?mode=json"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Lever board URL (the ``add-company`` UX)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host.endswith("lever.co"):
            raise ValueError(f"not a Lever board URL: {url!r}")
        segments = [segment for segment in parts.path.split("/") if segment]
        if not segments:
            raise ValueError("could not determine Lever account from URL")
        return cls(segments[0], client, company=company)

    async def fetch(self) -> list[Job]:
        response = await self._client.get(self._endpoint)
        response.raise_for_status()
        postings: list[dict[str, Any]] = response.json() or []
        return [self._to_job(posting) for posting in postings]

    def _to_job(self, posting: dict[str, Any]) -> Job:
        categories = posting.get("categories") or {}
        return Job(
            id=Job.make_id(_SOURCE, self._account, str(posting["id"])),
            source=_SOURCE,
            company=self._company,
            title=posting["text"],
            url=posting["hostedUrl"],
            location=categories.get("location") or None,
            posted_at=_epoch_ms_to_datetime(posting.get("createdAt")),
            raw=posting,
        )


def _epoch_ms_to_datetime(value: object) -> datetime | None:
    # bool is an int subclass; reject it so True/False don't become epoch 0/1.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)

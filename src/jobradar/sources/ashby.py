"""Ashby adapter — one class for every Ashby job board.

Ashby exposes a public JSON board API that returns all postings for a board in a
single call (no pagination):

    GET https://api.ashbyhq.com/posting-api/job-board/{slug}

The slug is the path segment of the public board URL
(``https://jobs.ashbyhq.com/{slug}``). Postings carry a real ``id`` and an ISO
``publishedAt``, so :attr:`Job.posted_at` is populated. Delisted postings
(``isListed == false``) are skipped.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "ashby"
_API_BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(JobSource):
    """Fetch postings from a single Ashby job board."""

    def __init__(
        self,
        slug: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> None:
        self._slug = slug
        self._client = client
        self._company = company or slug
        self._endpoint = f"{_API_BASE}/{slug}"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from an Ashby board URL (the ``add-company`` UX)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host.endswith("ashbyhq.com"):
            raise ValueError(f"not an Ashby board URL: {url!r}")
        segments = [segment for segment in parts.path.split("/") if segment]
        if not segments:
            raise ValueError("could not determine Ashby board slug from URL")
        return cls(segments[0], client, company=company)

    async def fetch(self) -> list[Job]:
        response = await self._client.get(self._endpoint)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        postings: list[dict[str, Any]] = data.get("jobs") or []
        return [self._to_job(p) for p in postings if p.get("isListed") is not False]

    def _to_job(self, posting: dict[str, Any]) -> Job:
        posting_id = str(posting["id"])
        fallback_url = f"https://jobs.ashbyhq.com/{self._slug}/{posting_id}"
        location = (posting.get("location") or "").strip()
        return Job(
            id=Job.make_id(_SOURCE, self._slug, posting_id),
            source=_SOURCE,
            company=self._company,
            title=posting["title"].strip(),  # Ashby titles can carry stray whitespace
            url=posting.get("jobUrl") or posting.get("applyUrl") or fallback_url,
            location=location or None,
            posted_at=_parse_timestamp(posting.get("publishedAt")),
            raw=posting,
        )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

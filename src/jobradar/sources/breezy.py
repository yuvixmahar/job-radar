"""Breezy adapter — one class for every Breezy HR careers site.

Breezy exposes a public JSON endpoint that returns all postings as a single
array (no pagination):

    GET https://{slug}.breezy.hr/json

Like Recruitee, the company slug is the *subdomain*. Postings carry an ISO
``published_date`` and a ``location`` object with a descriptive ``name``.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "breezy"


class BreezySource(JobSource):
    """Fetch postings from a single Breezy HR careers site."""

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
        self._endpoint = f"https://{slug}.breezy.hr/json"

    @classmethod
    def hosts(cls) -> tuple[str, ...]:
        return ("breezy.hr",)

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Breezy careers URL (the ``add-company`` UX).

        The slug is the subdomain: ``census.breezy.hr`` -> ``census``.
        """
        host = (urlsplit(url).hostname or "").lower()
        if not host.endswith(".breezy.hr"):
            raise ValueError(f"not a Breezy careers URL: {url!r}")
        slug = host.split(".")[0]
        if not slug:
            raise ValueError("could not determine Breezy slug from URL")
        return cls(slug, client, company=company)

    async def fetch(self) -> list[Job]:
        response = await self._client.get(self._endpoint)
        response.raise_for_status()
        postings: list[dict[str, Any]] = response.json() or []
        return [self._to_job(posting) for posting in postings]

    def _to_job(self, posting: dict[str, Any]) -> Job:
        posting_id = str(posting["id"])
        return Job(
            id=Job.make_id(_SOURCE, self._slug, posting_id),
            source=_SOURCE,
            company=self._company,
            title=(posting.get("name") or "").strip(),
            url=posting.get("url") or f"https://{self._slug}.breezy.hr/",
            location=_location(posting.get("location")),
            posted_at=_parse_timestamp(posting.get("published_date")),
            raw=posting,
        )


def _location(loc: object) -> str | None:
    if not isinstance(loc, dict):
        return None
    text = (loc.get("name") or "").strip()
    if not text:
        country = loc.get("country")
        if isinstance(country, dict):
            text = (country.get("name") or "").strip()
    return text or None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

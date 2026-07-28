"""Recruitee adapter — one class for every Recruitee careers site.

Recruitee exposes a public offers API that returns all postings in one call
(no pagination):

    GET https://{slug}.recruitee.com/api/offers/

Unlike most ATSs, the company slug is the *subdomain* of the careers URL, not a
path segment. Offers carry a ``published_at`` timestamp, but in a non-ISO format
(``"2026-07-24 09:54:08 UTC"``), which we parse into a UTC-aware datetime.
"""

from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "recruitee"


class RecruiteeSource(JobSource):
    """Fetch postings from a single Recruitee careers site."""

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
        self._endpoint = f"https://{slug}.recruitee.com/api/offers/"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Recruitee careers URL (the ``add-company`` UX).

        The slug is the subdomain: ``hardrockdigital.recruitee.com`` -> ``hardrockdigital``.
        """
        host = (urlsplit(url).hostname or "").lower()
        if not host.endswith(".recruitee.com"):
            raise ValueError(f"not a Recruitee careers URL: {url!r}")
        slug = host.split(".")[0]
        if not slug:
            raise ValueError("could not determine Recruitee slug from URL")
        return cls(slug, client, company=company)

    async def fetch(self) -> list[Job]:
        response = await self._client.get(self._endpoint)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        offers: list[dict[str, Any]] = data.get("offers") or []
        return [self._to_job(offer) for offer in offers]

    def _to_job(self, offer: dict[str, Any]) -> Job:
        posting_id = str(offer["id"])
        return Job(
            id=Job.make_id(_SOURCE, self._slug, posting_id),
            source=_SOURCE,
            company=self._company,
            title=(offer.get("title") or "").strip(),
            url=offer.get("careers_url") or f"https://{self._slug}.recruitee.com/",
            location=_location(offer),
            posted_at=_parse_timestamp(offer.get("published_at") or offer.get("created_at")),
            raw=offer,
        )


def _location(offer: dict[str, Any]) -> str | None:
    text = (offer.get("location") or "").strip()
    if not text:
        parts = [offer.get("city"), offer.get("country")]
        text = ", ".join(p for p in parts if p)
    if offer.get("remote"):
        text = f"{text} (Remote)" if text else "Remote"
    return text or None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace(" UTC", "").replace("Z", "+00:00").strip()
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

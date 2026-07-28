"""SmartRecruiters adapter — one class for every SmartRecruiters company.

SmartRecruiters exposes a public postings API, paginated by offset:

    GET https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset=0

Response is ``{"content": [...], "totalFound": N, ...}``; we page until we've
seen ``totalFound`` (same shape as Workday). The slug is the path segment of the
public careers URL and is *case-sensitive* (``AbbVie``), so it is not lowercased.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "smartrecruiters"
_API_BASE = "https://api.smartrecruiters.com/v1/companies"
_PAGE_SIZE = 100


class SmartRecruitersSource(JobSource):
    """Fetch postings from a single SmartRecruiters company."""

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
        self._endpoint = f"{_API_BASE}/{slug}/postings"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a SmartRecruiters careers URL (the ``add-company`` UX)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host.endswith("smartrecruiters.com"):
            raise ValueError(f"not a SmartRecruiters careers URL: {url!r}")
        segments = [segment for segment in parts.path.split("/") if segment]
        if not segments:
            raise ValueError("could not determine SmartRecruiters company from URL")
        return cls(segments[0], client, company=company)  # case-sensitive slug

    async def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        offset = 0
        while True:
            params = {"limit": _PAGE_SIZE, "offset": offset}
            response = await self._client.get(self._endpoint, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            postings: list[dict[str, Any]] = data.get("content") or []
            jobs.extend(self._to_job(posting) for posting in postings)

            offset += _PAGE_SIZE
            if not postings or offset >= int(data.get("totalFound", 0)):
                break
        return jobs

    def _to_job(self, posting: dict[str, Any]) -> Job:
        posting_id = str(posting["id"])
        return Job(
            id=Job.make_id(_SOURCE, self._slug, posting_id),
            source=_SOURCE,
            company=self._company,
            title=(posting.get("name") or "").strip(),
            url=f"https://jobs.smartrecruiters.com/{self._slug}/{posting_id}",
            location=_location(posting.get("location")),
            posted_at=_parse_timestamp(posting.get("releasedDate")),
            raw=posting,
        )


def _location(loc: object) -> str | None:
    if not isinstance(loc, dict):
        return None
    text = (loc.get("fullLocation") or "").strip()
    if not text:
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        text = ", ".join(str(p) for p in parts if p)
    if loc.get("remote"):
        text = f"{text} (Remote)" if text else "Remote"
    return text or None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

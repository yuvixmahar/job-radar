"""AMD adapter — AMD's own careers site (the Phenom People platform).

Like Amazon, AMD is a single company on one fixed endpoint (not per-tenant),
so there is no slug to parse:

    GET https://careers.amd.com/api/jobs
        ?page=1&limit=100&sortBy=posted_date&descending=true&internal=false

AMD has ~1,000 open roles. We sort by ``posted_date`` descending and read up to
``_MAX_JOBS`` — new postings (the only ones a watcher cares about) always sort to
the top, so the cap doesn't cost us anything that matters. ``limit=100`` keeps a
full snapshot to a handful of requests. Each entry is wrapped in ``{"data": ...}``
and job ids come from ``req_id``; keyword filtering still happens locally.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "amd"
_HOST = "careers.amd.com"
_URL = "https://careers.amd.com/api/jobs"
_PAGE_SIZE = 100
_MAX_JOBS = 500  # most-recent snapshot; new roles always sort to the top


class AMDSource(JobSource):
    """Fetch recent postings from AMD's careers site."""

    def __init__(self, client: httpx.AsyncClient, *, company: str | None = None) -> None:
        self._client = client
        self._company = company or "AMD"

    @classmethod
    def hosts(cls) -> tuple[str, ...]:
        return (_HOST,)

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a careers.amd.com URL (no slug — one feed)."""
        host = (urlsplit(url).hostname or "").lower()
        if host != _HOST and not host.endswith(f".{_HOST}"):
            raise ValueError(f"not an AMD careers URL: {url!r}")
        return cls(client, company=company)

    async def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        max_pages = _MAX_JOBS // _PAGE_SIZE
        for page in range(1, max_pages + 1):
            params: dict[str, str | int] = {
                "page": page,
                "limit": _PAGE_SIZE,
                "sortBy": "posted_date",
                "descending": "true",
                "internal": "false",
            }
            response = await self._client.get(_URL, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            entries: list[dict[str, Any]] = data.get("jobs") or []
            jobs.extend(self._to_job(entry) for entry in entries)

            total = data.get("totalCount")
            short_page = len(entries) < _PAGE_SIZE
            reached_total = isinstance(total, int) and page * _PAGE_SIZE >= total
            if short_page or reached_total:
                break
        return jobs

    def _to_job(self, entry: dict[str, Any]) -> Job:
        data = entry.get("data") if isinstance(entry.get("data"), dict) else entry
        job: dict[str, Any] = data or {}
        req_id = str(job.get("req_id") or job.get("slug") or "")
        return Job(
            id=Job.make_id(_SOURCE, "amd", req_id),
            source=_SOURCE,
            company=self._company,
            title=(job.get("title") or "").strip(),
            url=f"https://{_HOST}/careers-home/jobs/{req_id}"
            if req_id
            else f"https://{_HOST}/careers-home/jobs",
            location=_location(job),
            posted_at=_parse_posted(job.get("posted_date")),
            raw=entry,
        )


def _location(job: dict[str, Any]) -> str | None:
    for key in ("full_location", "short_location", "location_name"):
        text = (job.get(key) or "").strip()
        if text:
            return text
    return None


def _parse_posted(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:  # AMD sends e.g. "2026-07-31T06:22:00+0000" (offset without a colon)
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

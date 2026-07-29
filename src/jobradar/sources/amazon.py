"""Amazon adapter — Amazon's own global jobs search API.

Unlike the ATS adapters, Amazon is a single company on one fixed, worldwide
endpoint (not per-tenant):

    GET https://www.amazon.jobs/en/search.json?result_limit=100&offset=0&sort=recent

Amazon has ~10,000 open roles, so fetching *all* of them every poll would be
huge and impolite. We sort by ``recent`` and read up to ``_MAX_JOBS`` — new
postings (the only ones a watcher cares about) always sort to the top, so the cap
doesn't cost us anything that matters. Keyword filtering still happens locally.
"""

from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "amazon"
_URL = "https://www.amazon.jobs/en/search.json"
_PAGE_SIZE = 100
_MAX_JOBS = 500  # most-recent snapshot; new roles are always near the top


class AmazonSource(JobSource):
    """Fetch recent postings from Amazon's global jobs search."""

    def __init__(self, client: httpx.AsyncClient, *, company: str | None = None) -> None:
        self._client = client
        self._company = company or "Amazon"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from an amazon.jobs URL (no slug — one global feed)."""
        host = (urlsplit(url).hostname or "").lower()
        if not host.endswith("amazon.jobs"):
            raise ValueError(f"not an Amazon jobs URL: {url!r}")
        return cls(client, company=company)

    async def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for offset in range(0, _MAX_JOBS, _PAGE_SIZE):
            params: dict[str, str | int] = {
                "base_query": "",
                "result_limit": _PAGE_SIZE,
                "offset": offset,
                "sort": "recent",
            }
            response = await self._client.get(_URL, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            results: list[dict[str, Any]] = data.get("jobs") or []
            jobs.extend(self._to_job(job) for job in results)

            hits = data.get("hits")
            short_page = len(results) < _PAGE_SIZE
            reached_total = isinstance(hits, int) and offset + len(results) >= hits
            if short_page or reached_total:
                break
        return jobs

    def _to_job(self, job: dict[str, Any]) -> Job:
        path = job.get("job_path") or ""
        job_id = str(job.get("id_icims") or path or job.get("id") or "")
        return Job(
            id=Job.make_id(_SOURCE, "amazon", job_id),
            source=_SOURCE,
            company=self._company,
            title=(job.get("title") or "").strip(),
            url=f"https://www.amazon.jobs{path}" if path else "https://www.amazon.jobs",
            location=_location(job),
            posted_at=_parse_posted(job.get("posted_date")),
            raw=job,
        )


def _location(job: dict[str, Any]) -> str | None:
    text = (job.get("normalized_location") or "").strip()
    if text:
        return text
    parts = [job.get("city"), job.get("state"), job.get("country_code")]
    built = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
    if built:
        return built
    fallback = (job.get("location") or "").strip()
    return fallback or None


def _parse_posted(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None

"""Workable adapter — one class for every Workable account.

Workable exposes a public jobs API via POST, paginated with a ``nextPage`` token
echoed back in the next request body:

    POST https://apply.workable.com/api/v3/accounts/{slug}/jobs
    body {"query": "", "location": [], "department": [], "worktype": [], "remote": []}

Careers URLs come in two shapes: ``apply.workable.com/{slug}`` (slug in the path)
and ``{slug}.workable.com`` (slug in the subdomain); ``from_url`` handles both.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "workable"
_API_BASE = "https://apply.workable.com/api/v3/accounts"
_MAX_PAGES = 50  # safety cap against a token that never clears

# Hosts where the slug lives in the path, not the subdomain.
_PATH_SLUG_LABELS = {"apply", "www", "workable"}


class WorkableSource(JobSource):
    """Fetch postings from a single Workable account."""

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
        self._endpoint = f"{_API_BASE}/{slug}/jobs"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Workable careers URL (the ``add-company`` UX)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host.endswith("workable.com"):
            raise ValueError(f"not a Workable careers URL: {url!r}")
        first_label = host.split(".")[0]
        if first_label in _PATH_SLUG_LABELS:
            segments = [segment for segment in parts.path.split("/") if segment]
            if not segments:
                raise ValueError("could not determine Workable account from URL")
            slug = segments[0]
        else:
            slug = first_label  # {slug}.workable.com
        return cls(slug, client, company=company)

    async def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        token: str | None = None
        for _ in range(_MAX_PAGES):
            body: dict[str, Any] = {
                "query": "",
                "location": [],
                "department": [],
                "worktype": [],
                "remote": [],
            }
            if token:
                body["token"] = token
            response = await self._client.post(self._endpoint, json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            results: list[dict[str, Any]] = data.get("results") or []
            jobs.extend(self._to_job(posting) for posting in results)

            token = data.get("nextPage")
            if not token or not results:
                break
        return jobs

    def _to_job(self, posting: dict[str, Any]) -> Job:
        shortcode = str(posting["shortcode"])
        return Job(
            id=Job.make_id(_SOURCE, self._slug, shortcode),
            source=_SOURCE,
            company=self._company,
            title=(posting.get("title") or "").strip(),
            url=f"https://apply.workable.com/{self._slug}/j/{shortcode}/",
            location=_location(posting),
            posted_at=_parse_timestamp(posting.get("published")),
            raw=posting,
        )


def _location(posting: dict[str, Any]) -> str | None:
    loc = posting.get("location")
    text = ""
    if isinstance(loc, dict):
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        text = ", ".join(str(p) for p in parts if p)
    if posting.get("remote") or posting.get("workplace") == "remote":
        text = f"{text} (Remote)" if text else "Remote"
    return text or None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

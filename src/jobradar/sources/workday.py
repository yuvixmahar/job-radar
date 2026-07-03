"""Workday adapter — one class for every Workday tenant.

Workday hosts each company at ``{tenant}.{datacenter}.myworkdayjobs.com`` and
exposes a private-but-stable JSON API (the "CXS" endpoint) that its own careers
UI calls:

    POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body {"limit": 20, "offset": 0, "searchText": "", "appliedFacets": {}}

We page through it by bumping ``offset`` until ``total`` is reached. The HTTP
client is injected (the runner owns one shared, politely-configured
``httpx.AsyncClient``), so this adapter only knows how to build requests and
normalize the JSON into :class:`~jobradar.models.Job` objects.
"""

import re
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_PAGE_SIZE = 20
_SOURCE = "workday"
# A path segment like "en-US" / "fr-CA" that precedes the real site name.
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


class WorkdaySource(JobSource):
    """Fetch postings from a single Workday tenant/site."""

    def __init__(
        self,
        tenant: str,
        datacenter: str,
        site: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> None:
        self._tenant = tenant
        self._site = site
        self._client = client
        self._company = company or tenant
        self._host = f"{tenant}.{datacenter}.myworkdayjobs.com"
        self._endpoint = f"https://{self._host}/wday/cxs/{tenant}/{site}/jobs"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Workday careers URL (the ``add-company`` UX)."""
        host = urlsplit(url).netloc.lower()
        if not host.endswith(".myworkdayjobs.com"):
            raise ValueError(f"not a Workday careers URL: {url!r}")
        labels = host.split(".")
        if len(labels) < 4:
            raise ValueError(f"cannot parse tenant/datacenter from host: {host!r}")
        tenant, datacenter = labels[0], labels[1]
        site = _site_from_path(urlsplit(url).path)
        return cls(tenant, datacenter, site, client, company=company)

    async def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        offset = 0
        while True:
            payload = {
                "limit": _PAGE_SIZE,
                "offset": offset,
                "searchText": "",
                "appliedFacets": {},
            }
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            postings: list[dict[str, Any]] = data.get("jobPostings") or []
            jobs.extend(self._to_job(posting) for posting in postings)

            offset += _PAGE_SIZE
            if not postings or offset >= int(data.get("total", 0)):
                break
        return jobs

    def _to_job(self, posting: dict[str, Any]) -> Job:
        external_path = posting.get("externalPath", "")
        bullet_fields = posting.get("bulletFields") or []
        # bulletFields[0] is the requisition id (e.g. "R-12345"); fall back to
        # the URL path when a tenant doesn't expose it.
        req_id = bullet_fields[0] if bullet_fields else external_path
        return Job(
            id=Job.make_id(_SOURCE, self._tenant, req_id),
            source=_SOURCE,
            company=self._company,
            title=posting["title"],
            url=f"https://{self._host}/{self._site}{external_path}",
            location=posting.get("locationsText") or None,
            posted_at=None,  # Workday only gives relative text ("Posted 3 Days Ago")
            raw=posting,
        )


def _site_from_path(path: str) -> str:
    """Extract the Workday site name from a careers URL path.

    ``/en-US/Careers`` and ``/Careers/job/...`` both yield ``"Careers"``.
    """
    segments = [segment for segment in path.split("/") if segment]
    if segments and _LOCALE.match(segments[0]):
        segments = segments[1:]
    if not segments:
        raise ValueError(f"could not determine Workday site from path: {path!r}")
    return segments[0]

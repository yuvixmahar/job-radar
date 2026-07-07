"""Greenhouse adapter — one class for every Greenhouse job board.

Greenhouse exposes a clean, public JSON board API that returns *all* postings for
a board in a single call (no pagination):

    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs

The board token is the last path segment of the public board URL
(``https://boards.greenhouse.io/{board_token}``). Unlike Workday, Greenhouse gives
a real ``updated_at`` timestamp, so we can populate :attr:`Job.posted_at`.
"""

from datetime import datetime
from typing import Any, Self
from urllib.parse import parse_qs, urlsplit

import httpx

from jobradar.models import Job
from jobradar.sources.base import JobSource

_SOURCE = "greenhouse"
_API_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(JobSource):
    """Fetch postings from a single Greenhouse job board."""

    def __init__(
        self,
        board_token: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> None:
        self._token = board_token
        self._client = client
        self._company = company or board_token
        self._endpoint = f"{_API_BASE}/{board_token}/jobs"

    @classmethod
    def from_url(
        cls,
        url: str,
        client: httpx.AsyncClient,
        *,
        company: str | None = None,
    ) -> Self:
        """Build a source from a Greenhouse board URL (the ``add-company`` UX)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host.endswith("greenhouse.io"):
            raise ValueError(f"not a Greenhouse board URL: {url!r}")
        token = _board_token_from_url(parts.path, parts.query)
        return cls(token, client, company=company)

    async def fetch(self) -> list[Job]:
        response = await self._client.get(self._endpoint)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        postings: list[dict[str, Any]] = data.get("jobs") or []
        return [self._to_job(posting) for posting in postings]

    def _to_job(self, posting: dict[str, Any]) -> Job:
        location = posting.get("location") or {}
        return Job(
            id=Job.make_id(_SOURCE, self._token, str(posting["id"])),
            source=_SOURCE,
            company=self._company,
            title=posting["title"],
            url=posting["absolute_url"],
            location=location.get("name") or None,
            posted_at=_parse_timestamp(posting.get("updated_at")),
            raw=posting,
        )


def _board_token_from_url(path: str, query: str) -> str:
    """Extract the board token from a Greenhouse URL path or ``?for=`` query.

    ``/airbnb`` and ``/airbnb/jobs/123`` yield ``"airbnb"``; embedded boards use
    ``/embed/job_board?for=airbnb``.
    """
    for_param = parse_qs(query).get("for")
    if for_param:
        return for_param[0]
    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[0] != "embed":
        return segments[0]
    raise ValueError("could not determine Greenhouse board token from URL")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

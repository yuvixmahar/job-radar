from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.smartrecruiters import SmartRecruitersSource

ENDPOINT = "https://api.smartrecruiters.com/v1/companies/AbbVie/postings"


def posting(
    *,
    id: str = "3743990014308876",
    name: str = "Pharmaceutical Operator",
    location: dict[str, Any] | None = None,
    released_date: str | None = "2026-07-28T04:02:27.348Z",
) -> dict[str, Any]:
    if location is None:
        location = {
            "city": "Barceloneta",
            "country": "pr",
            "fullLocation": "Barceloneta, Puerto Rico",
        }
    return {"id": id, "name": name, "location": location, "releasedDate": released_date}


def page(ids: list[str], total: int) -> dict[str, Any]:
    return {"totalFound": total, "content": [posting(id=i) for i in ids]}


# --- URL parsing (pure) ---


async def test_from_url_parses_case_sensitive_slug() -> None:
    async with httpx.AsyncClient() as client:
        source = SmartRecruitersSource.from_url(
            "https://careers.smartrecruiters.com/AbbVie", client
        )
    assert source._endpoint == ENDPOINT  # "AbbVie" case preserved


async def test_from_url_rejects_non_smartrecruiters_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            SmartRecruitersSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"totalFound": 1, "content": [posting()]})
    )
    async with httpx.AsyncClient() as client:
        source = SmartRecruitersSource("AbbVie", client, company="AbbVie")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "smartrecruiters:AbbVie:3743990014308876"
    assert job.source == "smartrecruiters"
    assert job.company == "AbbVie"
    assert job.title == "Pharmaceutical Operator"
    assert job.url == "https://jobs.smartrecruiters.com/AbbVie/3743990014308876"
    assert job.location == "Barceloneta, Puerto Rico"
    assert job.posted_at == datetime.fromisoformat("2026-07-28T04:02:27.348+00:00")


@respx.mock
async def test_location_built_from_parts_when_no_full_location() -> None:
    loc = {"city": "Austin", "region": "TX", "country": "us"}
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"totalFound": 1, "content": [posting(location=loc)]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await SmartRecruitersSource("AbbVie", client).fetch()
    assert jobs[0].location == "Austin, TX, us"


@respx.mock
async def test_remote_flag_is_appended() -> None:
    loc = {"fullLocation": "Austin, TX", "remote": True}
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"totalFound": 1, "content": [posting(location=loc)]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await SmartRecruitersSource("AbbVie", client).fetch()
    assert jobs[0].location == "Austin, TX (Remote)"


# --- fetch: pagination ---


@respx.mock
async def test_fetch_paginates_by_offset() -> None:
    page1 = page([str(i) for i in range(100)], total=150)
    page2 = page([str(i) for i in range(100, 150)], total=150)
    route = respx.get(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        jobs = await SmartRecruitersSource("AbbVie", client).fetch()

    assert len(jobs) == 150
    assert route.call_count == 2
    assert route.calls[0].request.url.params["offset"] == "0"
    assert route.calls[1].request.url.params["offset"] == "100"


@respx.mock
async def test_fetch_stops_on_empty_page() -> None:
    page1 = page([str(i) for i in range(100)], total=999)  # claims 999...
    page2 = {"totalFound": 999, "content": []}  # ...but nothing more
    route = respx.get(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        jobs = await SmartRecruitersSource("AbbVie", client).fetch()

    assert len(jobs) == 100
    assert route.call_count == 2


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await SmartRecruitersSource("AbbVie", client).fetch()

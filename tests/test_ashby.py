from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.ashby import AshbySource

ENDPOINT = "https://api.ashbyhq.com/posting-api/job-board/Ramp"


def posting(
    *,
    id: str = "34413f8d-26bf-4bbc-8ade-eb309a0e2245",
    title: str = "Security Engineer",
    location: str | None = "New York, NY",
    published_at: str | None = "2026-04-07T17:12:35.753+00:00",
    is_listed: bool = True,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "location": location,
        "publishedAt": published_at,
        "isListed": is_listed,
        "jobUrl": f"https://jobs.ashbyhq.com/Ramp/{id}",
    }


# --- URL parsing (pure) ---


async def test_from_url_parses_slug() -> None:
    async with httpx.AsyncClient() as client:
        source = AshbySource.from_url("https://jobs.ashbyhq.com/Ramp", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_ashby_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            AshbySource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [posting()]}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client, company="Ramp")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "ashby:Ramp:34413f8d-26bf-4bbc-8ade-eb309a0e2245"
    assert job.source == "ashby"
    assert job.company == "Ramp"
    assert job.title == "Security Engineer"
    assert job.url == "https://jobs.ashbyhq.com/Ramp/34413f8d-26bf-4bbc-8ade-eb309a0e2245"
    assert job.location == "New York, NY"
    assert job.posted_at == datetime.fromisoformat("2026-04-07T17:12:35.753+00:00")


@respx.mock
async def test_title_and_location_are_stripped() -> None:
    p = posting(title="  Security Engineer  ", location="  New York, NY  ")
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [p]}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()
    assert jobs[0].title == "Security Engineer"
    assert jobs[0].location == "New York, NY"


@respx.mock
async def test_company_defaults_to_slug() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [posting()]}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()
    assert jobs[0].company == "Ramp"


@respx.mock
async def test_delisted_postings_are_skipped() -> None:
    jobs_json = [posting(id="a", is_listed=True), posting(id="b", is_listed=False)]
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": jobs_json}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()
    assert [j.id for j in jobs] == ["ashby:Ramp:a"]


@respx.mock
async def test_missing_location_and_timestamp_become_none() -> None:
    p = posting(location=None, published_at=None)
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [p]}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()
    assert jobs[0].location is None
    assert jobs[0].posted_at is None


@respx.mock
async def test_url_falls_back_to_constructed_board_url() -> None:
    p = {"id": "x1", "title": "Engineer", "isListed": True}  # no jobUrl/applyUrl
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [p]}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()
    assert jobs[0].url == "https://jobs.ashbyhq.com/Ramp/x1"


@respx.mock
async def test_fetch_returns_all_jobs_in_one_call() -> None:
    body = [posting(id="a"), posting(id="b"), posting(id="c")]
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": body}))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        jobs = await source.fetch()

    assert [j.id for j in jobs] == ["ashby:Ramp:a", "ashby:Ramp:b", "ashby:Ramp:c"]
    assert route.call_count == 1  # no pagination


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        source = AshbySource("Ramp", client)
        with pytest.raises(httpx.HTTPStatusError):
            await source.fetch()

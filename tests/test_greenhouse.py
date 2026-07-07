from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.greenhouse import GreenhouseSource

ENDPOINT = "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs"


def posting(
    *,
    id: int = 123,
    title: str = "Backend Engineer",
    location: str | None = "Remote",
    updated_at: str | None = "2024-01-15T10:30:00-05:00",
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "absolute_url": f"https://boards.greenhouse.io/airbnb/jobs/{id}",
        "location": {"name": location} if location is not None else None,
        "updated_at": updated_at,
    }


# --- URL parsing (pure) ---


async def test_from_url_parses_token_from_path() -> None:
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource.from_url("https://boards.greenhouse.io/airbnb", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_accepts_embed_for_param() -> None:
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource.from_url(
            "https://boards.greenhouse.io/embed/job_board?for=airbnb", client
        )
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_greenhouse_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            GreenhouseSource.from_url("https://ciena.wd5.myworkdayjobs.com/Careers", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"jobs": [posting()], "meta": {"total": 1}})
    )
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client, company="Airbnb")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "greenhouse:airbnb:123"
    assert job.source == "greenhouse"
    assert job.company == "Airbnb"
    assert job.title == "Backend Engineer"
    assert job.url == "https://boards.greenhouse.io/airbnb/jobs/123"
    assert job.location == "Remote"
    assert job.posted_at == datetime.fromisoformat("2024-01-15T10:30:00-05:00")


@respx.mock
async def test_company_defaults_to_board_token() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [posting()]}))
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client)
        jobs = await source.fetch()
    assert jobs[0].company == "airbnb"


@respx.mock
async def test_missing_location_and_timestamp_become_none() -> None:
    p = posting(location=None, updated_at=None)
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [p]}))
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client)
        jobs = await source.fetch()
    assert jobs[0].location is None
    assert jobs[0].posted_at is None


@respx.mock
async def test_fetch_returns_all_jobs_in_one_call() -> None:
    jobs_json = [posting(id=1), posting(id=2), posting(id=3)]
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": jobs_json}))
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client)
        jobs = await source.fetch()

    assert [j.id for j in jobs] == [
        "greenhouse:airbnb:1",
        "greenhouse:airbnb:2",
        "greenhouse:airbnb:3",
    ]
    assert route.call_count == 1  # no pagination


@respx.mock
async def test_empty_board_returns_no_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": []}))
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client)
        assert await source.fetch() == []


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        source = GreenhouseSource("airbnb", client)
        with pytest.raises(httpx.HTTPStatusError):
            await source.fetch()

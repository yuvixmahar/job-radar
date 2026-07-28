from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.recruitee import RecruiteeSource

ENDPOINT = "https://hardrockdigital.recruitee.com/api/offers/"


def offer(
    *,
    id: int = 2688839,
    title: str = "Analyst - Fraud",
    location: str | None = "Atlantic City, NJ, United States",
    published_at: str | None = "2026-07-24 09:54:08 UTC",
    remote: bool = False,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "location": location,
        "city": "Atlantic City",
        "country": "United States",
        "published_at": published_at,
        "created_at": "2026-07-24 09:50:20 UTC",
        "remote": remote,
        "careers_url": f"https://hardrockdigital.recruitee.com/o/analyst-fraud-{id}",
    }


# --- URL parsing (pure): slug is the subdomain ---


async def test_from_url_parses_slug_from_subdomain() -> None:
    async with httpx.AsyncClient() as client:
        source = RecruiteeSource.from_url("https://hardrockdigital.recruitee.com", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_recruitee_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            RecruiteeSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"offers": [offer()]}))
    async with httpx.AsyncClient() as client:
        source = RecruiteeSource("hardrockdigital", client, company="Hard Rock Digital")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "recruitee:hardrockdigital:2688839"
    assert job.source == "recruitee"
    assert job.company == "Hard Rock Digital"
    assert job.title == "Analyst - Fraud"
    assert job.url == "https://hardrockdigital.recruitee.com/o/analyst-fraud-2688839"
    assert job.location == "Atlantic City, NJ, United States"
    assert job.posted_at == datetime(2026, 7, 24, 9, 54, 8, tzinfo=UTC)


@respx.mock
async def test_non_iso_utc_timestamp_is_parsed() -> None:
    o = offer(published_at="2026-01-02 03:04:05 UTC")
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"offers": [o]}))
    async with httpx.AsyncClient() as client:
        jobs = await RecruiteeSource("hardrockdigital", client).fetch()
    assert jobs[0].posted_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@respx.mock
async def test_bad_timestamp_becomes_none() -> None:
    o = offer(published_at="not a date")
    o["created_at"] = "also bad"
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"offers": [o]}))
    async with httpx.AsyncClient() as client:
        jobs = await RecruiteeSource("hardrockdigital", client).fetch()
    assert jobs[0].posted_at is None


@respx.mock
async def test_location_falls_back_to_city_country() -> None:
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"offers": [offer(location=None)]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await RecruiteeSource("hardrockdigital", client).fetch()
    assert jobs[0].location == "Atlantic City, United States"


@respx.mock
async def test_remote_flag_is_appended() -> None:
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(
            200, json={"offers": [offer(location="Remote-first", remote=True)]}
        )
    )
    async with httpx.AsyncClient() as client:
        jobs = await RecruiteeSource("hardrockdigital", client).fetch()
    assert jobs[0].location == "Remote-first (Remote)"


@respx.mock
async def test_fetch_returns_all_offers_in_one_call() -> None:
    body = [offer(id=1), offer(id=2), offer(id=3)]
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"offers": body}))
    async with httpx.AsyncClient() as client:
        jobs = await RecruiteeSource("hardrockdigital", client).fetch()

    assert [j.id for j in jobs] == [
        "recruitee:hardrockdigital:1",
        "recruitee:hardrockdigital:2",
        "recruitee:hardrockdigital:3",
    ]
    assert route.call_count == 1


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await RecruiteeSource("hardrockdigital", client).fetch()

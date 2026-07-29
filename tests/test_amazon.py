from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.amazon import AmazonSource

URL = "https://www.amazon.jobs/en/search.json"


def job(
    *,
    id_icims: str = "10486909",
    title: str = "Data Center Engineer",
    normalized: str | None = "Hyderabad, Telangana, IND",
    city: str = "Hyderabad",
    state: str = "TS",
    country: str = "IND",
    posted: str | None = "July 29, 2026",
) -> dict[str, Any]:
    return {
        "id_icims": id_icims,
        "job_path": f"/en/jobs/{id_icims}/role",
        "title": title,
        "normalized_location": normalized,
        "city": city,
        "state": state,
        "country_code": country,
        "location": "IN, TS, Hyderabad",
        "posted_date": posted,
    }


# --- from_url: no slug, one global feed ---


async def test_from_url_accepts_amazon_jobs_host() -> None:
    async with httpx.AsyncClient() as client:
        source = AmazonSource.from_url("https://www.amazon.jobs/en/search", client)
    assert isinstance(source, AmazonSource)


async def test_from_url_rejects_non_amazon_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            AmazonSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"hits": 1, "jobs": [job()]}))
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "amazon:amazon:10486909"
    assert j.source == "amazon"
    assert j.company == "Amazon"
    assert j.title == "Data Center Engineer"
    assert j.url == "https://www.amazon.jobs/en/jobs/10486909/role"
    assert j.location == "Hyderabad, Telangana, IND"
    assert j.posted_at == datetime(2026, 7, 29, tzinfo=UTC)


@respx.mock
async def test_location_falls_back_to_structured_fields() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"hits": 1, "jobs": [job(normalized=None)]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()
    assert jobs[0].location == "Hyderabad, TS, IND"


@respx.mock
async def test_iso_posted_date_is_parsed() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"hits": 1, "jobs": [job(posted="2026-01-15")]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()
    assert jobs[0].posted_at == datetime(2026, 1, 15, tzinfo=UTC)


@respx.mock
async def test_bad_posted_date_becomes_none() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"hits": 1, "jobs": [job(posted="whenever")]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()
    assert jobs[0].posted_at is None


# --- fetch: pagination ---


@respx.mock
async def test_fetch_paginates_by_offset() -> None:
    page1 = {"hits": 150, "jobs": [job(id_icims=str(i)) for i in range(100)]}
    page2 = {"hits": 150, "jobs": [job(id_icims=str(i)) for i in range(100, 150)]}
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()

    assert len(jobs) == 150
    assert route.call_count == 2
    assert route.calls[0].request.url.params["offset"] == "0"
    assert route.calls[1].request.url.params["offset"] == "100"


@respx.mock
async def test_fetch_stops_on_short_page() -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, json={"hits": 9999, "jobs": [job()]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()
    assert len(jobs) == 1
    assert route.call_count == 1  # short page ends it, despite hits=9999


@respx.mock
async def test_fetch_respects_max_jobs_cap() -> None:
    full_page = {"hits": 10000, "jobs": [job(id_icims=str(i)) for i in range(100)]}
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=full_page))
    async with httpx.AsyncClient() as client:
        jobs = await AmazonSource(client).fetch()

    assert route.call_count == 5  # _MAX_JOBS (500) / _PAGE_SIZE (100)
    assert len(jobs) == 500


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await AmazonSource(client).fetch()

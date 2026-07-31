from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.amd import AMDSource

URL = "https://careers.amd.com/api/jobs"


def job(
    *,
    req_id: str = "89163",
    title: str = "Silicon Design Engineer",
    full_location: str | None = "Shanghai, China",
    location_name: str = "CN,Shanghai-Design Ctr B1",
    posted: str | None = "2026-07-31T06:22:00+0000",
) -> dict[str, Any]:
    return {
        "data": {
            "slug": req_id,
            "req_id": req_id,
            "title": title,
            "full_location": full_location,
            "short_location": full_location,
            "location_name": location_name,
            "posted_date": posted,
        }
    }


# --- from_url: no slug, one feed ---


async def test_from_url_accepts_amd_careers_host() -> None:
    async with httpx.AsyncClient() as client:
        source = AMDSource.from_url("https://careers.amd.com/careers-home/jobs", client)
    assert isinstance(source, AMDSource)


async def test_from_url_rejects_non_amd_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            AMDSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"totalCount": 1, "jobs": [job()]}))
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "amd:amd:89163"
    assert j.source == "amd"
    assert j.company == "AMD"
    assert j.title == "Silicon Design Engineer"
    assert j.url == "https://careers.amd.com/careers-home/jobs/89163"
    assert j.location == "Shanghai, China"
    assert j.posted_at == datetime(2026, 7, 31, 6, 22, tzinfo=UTC)


@respx.mock
async def test_company_override() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"totalCount": 1, "jobs": [job()]}))
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client, company="Advanced Micro Devices").fetch()
    assert jobs[0].company == "Advanced Micro Devices"


@respx.mock
async def test_location_falls_back_to_location_name() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"totalCount": 1, "jobs": [job(full_location=None)]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()
    assert jobs[0].location == "CN,Shanghai-Design Ctr B1"


@respx.mock
async def test_bad_posted_date_becomes_none() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"totalCount": 1, "jobs": [job(posted="whenever")]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()
    assert jobs[0].posted_at is None


# --- fetch: pagination ---


@respx.mock
async def test_fetch_paginates_by_page() -> None:
    page1 = {"totalCount": 150, "jobs": [job(req_id=str(i)) for i in range(100)]}
    page2 = {"totalCount": 150, "jobs": [job(req_id=str(i)) for i in range(100, 150)]}
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()

    assert len(jobs) == 150
    assert route.call_count == 2
    assert route.calls[0].request.url.params["page"] == "1"
    assert route.calls[1].request.url.params["page"] == "2"


@respx.mock
async def test_fetch_stops_on_short_page() -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, json={"totalCount": 9999, "jobs": [job()]})
    )
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()
    assert len(jobs) == 1
    assert route.call_count == 1  # short page ends it, despite totalCount=9999


@respx.mock
async def test_fetch_respects_max_jobs_cap() -> None:
    full_page = {"totalCount": 10000, "jobs": [job(req_id=str(i)) for i in range(100)]}
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=full_page))
    async with httpx.AsyncClient() as client:
        jobs = await AMDSource(client).fetch()

    assert route.call_count == 5  # _MAX_JOBS (500) / _PAGE_SIZE (100)
    assert len(jobs) == 500


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await AMDSource(client).fetch()

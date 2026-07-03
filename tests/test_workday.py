import json
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.workday import WorkdaySource, _site_from_path

ENDPOINT = "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/jobs"


def posting(
    *,
    req: str = "R-1",
    title: str = "Firmware Engineer",
    path: str = "/job/Ottawa/Firmware_R-1",
    location: str | None = "Ottawa, Canada",
) -> dict[str, Any]:
    return {
        "title": title,
        "externalPath": path,
        "bulletFields": [req],
        "locationsText": location,
        "postedOn": "Posted 3 Days Ago",
    }


def page(reqs: list[str], total: int) -> dict[str, Any]:
    return {"total": total, "jobPostings": [posting(req=r, path=f"/job/{r}") for r in reqs]}


# --- URL path parsing (pure, no HTTP) ---


def test_site_from_path_strips_locale() -> None:
    assert _site_from_path("/en-US/Careers") == "Careers"
    assert _site_from_path("/Careers/job/x") == "Careers"


def test_site_from_path_raises_when_empty() -> None:
    with pytest.raises(ValueError):
        _site_from_path("/")


# --- fetch: normalization ---


@respx.mock
async def test_fetch_single_page_normalizes_jobs() -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 1, "jobPostings": [posting()]})
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client, company="Ciena")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "workday:ciena:R-1"
    assert job.source == "workday"
    assert job.company == "Ciena"
    assert job.title == "Firmware Engineer"
    assert job.url == "https://ciena.wd5.myworkdayjobs.com/Careers/job/Ottawa/Firmware_R-1"
    assert job.location == "Ottawa, Canada"
    assert job.posted_at is None
    assert job.raw is not None


@respx.mock
async def test_company_defaults_to_tenant() -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 1, "jobPostings": [posting()]})
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client)
        jobs = await source.fetch()
    assert jobs[0].company == "ciena"


@respx.mock
async def test_id_falls_back_to_external_path_without_bulletfields() -> None:
    p = {"title": "Staff Engineer", "externalPath": "/job/Foo_R-9", "locationsText": None}
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 1, "jobPostings": [p]})
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client)
        jobs = await source.fetch()
    assert jobs[0].id == "workday:ciena:/job/Foo_R-9"
    assert jobs[0].location is None


# --- fetch: pagination ---


@respx.mock
async def test_fetch_paginates_until_total_reached() -> None:
    page1 = page([f"R-{i}" for i in range(20)], total=25)
    page2 = page([f"R-{i}" for i in range(20, 25)], total=25)
    route = respx.post(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client)
        jobs = await source.fetch()

    assert len(jobs) == 25
    assert route.call_count == 2
    first = json.loads(route.calls[0].request.content)
    second = json.loads(route.calls[1].request.content)
    assert first["offset"] == 0
    assert second["offset"] == 20


@respx.mock
async def test_fetch_stops_on_empty_page_even_if_total_lies() -> None:
    page1 = page([f"R-{i}" for i in range(20)], total=100)  # claims 100...
    page2 = {"total": 100, "jobPostings": []}  # ...but nothing more comes
    route = respx.post(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client)
        jobs = await source.fetch()

    assert len(jobs) == 20
    assert route.call_count == 2


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        source = WorkdaySource("ciena", "wd5", "Careers", client)
        with pytest.raises(httpx.HTTPStatusError):
            await source.fetch()


# --- from_url ---


@respx.mock
async def test_from_url_parses_tenant_datacenter_site() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 0, "jobPostings": []})
    )
    async with httpx.AsyncClient() as client:
        source = WorkdaySource.from_url("https://ciena.wd5.myworkdayjobs.com/en-US/Careers", client)
        await source.fetch()
    assert route.called  # it hit exactly the endpoint we mocked


async def test_from_url_rejects_non_workday_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            WorkdaySource.from_url("https://boards.greenhouse.io/acme", client)

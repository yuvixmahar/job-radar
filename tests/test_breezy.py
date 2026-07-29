from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.breezy import BreezySource

ENDPOINT = "https://census.breezy.hr/json"


def posting(
    *,
    id: str = "05c93e26908b01",
    name: str = "Application Security Lead",
    location: dict[str, Any] | None = None,
    published_date: str | None = "2026-06-30T09:54:11.226Z",
) -> dict[str, Any]:
    if location is None:
        location = {"name": "Worldwide", "is_remote": True, "country": {"name": "Worldwide"}}
    return {
        "id": id,
        "name": name,
        "url": f"https://census.breezy.hr/p/{id}",
        "location": location,
        "published_date": published_date,
        "salary": "",
    }


# --- URL parsing (pure): slug is the subdomain ---


async def test_from_url_parses_slug_from_subdomain() -> None:
    async with httpx.AsyncClient() as client:
        source = BreezySource.from_url("https://census.breezy.hr", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_breezy_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            BreezySource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting()]))
    async with httpx.AsyncClient() as client:
        source = BreezySource("census", client, company="Census")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "breezy:census:05c93e26908b01"
    assert job.source == "breezy"
    assert job.company == "Census"
    assert job.title == "Application Security Lead"
    assert job.url == "https://census.breezy.hr/p/05c93e26908b01"
    assert job.location == "Worldwide"
    assert job.posted_at == datetime.fromisoformat("2026-06-30T09:54:11.226+00:00")


@respx.mock
async def test_location_falls_back_to_country_name() -> None:
    loc = {"name": "", "country": {"name": "United States"}}
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting(location=loc)]))
    async with httpx.AsyncClient() as client:
        jobs = await BreezySource("census", client).fetch()
    assert jobs[0].location == "United States"


@respx.mock
async def test_non_dict_location_becomes_none() -> None:
    p = posting()
    p["location"] = "somewhere"  # not an object
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[p]))
    async with httpx.AsyncClient() as client:
        jobs = await BreezySource("census", client).fetch()
    assert jobs[0].location is None


@respx.mock
async def test_fetch_returns_all_postings_in_one_call() -> None:
    body = [posting(id="a"), posting(id="b"), posting(id="c")]
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    async with httpx.AsyncClient() as client:
        jobs = await BreezySource("census", client).fetch()

    assert [j.id for j in jobs] == ["breezy:census:a", "breezy:census:b", "breezy:census:c"]
    assert route.call_count == 1


@respx.mock
async def test_empty_board_returns_no_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient() as client:
        assert await BreezySource("census", client).fetch() == []


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await BreezySource("census", client).fetch()

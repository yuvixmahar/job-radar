from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.lever import LeverSource

ENDPOINT = "https://api.lever.co/v0/postings/leverdemo?mode=json"


def posting(
    *,
    id: str = "33538a2f-d27d-4a96-8f05-fa4b0e4d940e",
    text: str = "Backend Engineer",
    location: str | None = "Remote",
    created_at: object = 1553186035299,
) -> dict[str, Any]:
    return {
        "id": id,
        "text": text,
        "hostedUrl": f"https://jobs.lever.co/leverdemo/{id}",
        "categories": {"location": location} if location is not None else {},
        "createdAt": created_at,
    }


# --- URL parsing (pure) ---


async def test_from_url_parses_account() -> None:
    async with httpx.AsyncClient() as client:
        source = LeverSource.from_url("https://jobs.lever.co/leverdemo", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_lever_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            LeverSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting()]))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client, company="Lever Demo")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "lever:leverdemo:33538a2f-d27d-4a96-8f05-fa4b0e4d940e"
    assert job.source == "lever"
    assert job.company == "Lever Demo"
    assert job.title == "Backend Engineer"
    assert job.url == "https://jobs.lever.co/leverdemo/33538a2f-d27d-4a96-8f05-fa4b0e4d940e"
    assert job.location == "Remote"
    assert job.posted_at == datetime.fromtimestamp(1553186035299 / 1000, tz=UTC)


@respx.mock
async def test_company_defaults_to_account() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting()]))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        jobs = await source.fetch()
    assert jobs[0].company == "leverdemo"


@respx.mock
async def test_missing_location_becomes_none() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting(location=None)]))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        jobs = await source.fetch()
    assert jobs[0].location is None


@respx.mock
async def test_non_numeric_created_at_becomes_none() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[posting(created_at="nope")]))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        jobs = await source.fetch()
    assert jobs[0].posted_at is None


@respx.mock
async def test_fetch_returns_all_jobs_in_one_call() -> None:
    body = [posting(id="a"), posting(id="b"), posting(id="c")]
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        jobs = await source.fetch()

    assert [j.id for j in jobs] == [
        "lever:leverdemo:a",
        "lever:leverdemo:b",
        "lever:leverdemo:c",
    ]
    assert route.call_count == 1  # no pagination


@respx.mock
async def test_empty_board_returns_no_jobs() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        assert await source.fetch() == []


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        source = LeverSource("leverdemo", client)
        with pytest.raises(httpx.HTTPStatusError):
            await source.fetch()

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
import respx

from jobradar.sources.workable import WorkableSource

ENDPOINT = "https://apply.workable.com/api/v3/accounts/huggingface/jobs"


def posting(
    *,
    shortcode: str = "F8427A442D",
    title: str = "Senior Python Engineer",
    country: str | None = "United States",
    city: str = "",
    region: str | None = None,
    remote: bool = True,
    published: str | None = "2026-06-02T00:00:00.000Z",
) -> dict[str, Any]:
    return {
        "id": 5856207,
        "shortcode": shortcode,
        "title": title,
        "remote": remote,
        "location": {"country": country, "city": city, "region": region},
        "published": published,
    }


# --- URL parsing (pure): both host shapes ---


async def test_from_url_parses_slug_from_apply_path() -> None:
    async with httpx.AsyncClient() as client:
        source = WorkableSource.from_url("https://apply.workable.com/huggingface", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_parses_slug_from_subdomain() -> None:
    async with httpx.AsyncClient() as client:
        source = WorkableSource.from_url("https://huggingface.workable.com", client)
    assert source._endpoint == ENDPOINT


async def test_from_url_rejects_non_workable_host() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            WorkableSource.from_url("https://boards.greenhouse.io/acme", client)


# --- fetch: normalization ---


@respx.mock
async def test_fetch_normalizes_jobs() -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 1, "results": [posting()]})
    )
    async with httpx.AsyncClient() as client:
        source = WorkableSource("huggingface", client, company="Hugging Face")
        jobs = await source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "workable:huggingface:F8427A442D"
    assert job.source == "workable"
    assert job.company == "Hugging Face"
    assert job.title == "Senior Python Engineer"
    assert job.url == "https://apply.workable.com/huggingface/j/F8427A442D/"
    assert job.location == "United States (Remote)"
    assert job.posted_at == datetime.fromisoformat("2026-06-02T00:00:00.000+00:00")


@respx.mock
async def test_location_without_remote_is_built_from_parts() -> None:
    p = posting(city="Austin", region="TX", country="United States", remote=False)
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"results": [p]}))
    async with httpx.AsyncClient() as client:
        jobs = await WorkableSource("huggingface", client).fetch()
    assert jobs[0].location == "Austin, TX, United States"


# --- fetch: token pagination ---


@respx.mock
async def test_fetch_follows_next_page_token() -> None:
    page1 = {"results": [posting(shortcode="a")], "nextPage": "TOK2"}
    page2 = {"results": [posting(shortcode="b")], "nextPage": None}
    route = respx.post(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as client:
        jobs = await WorkableSource("huggingface", client).fetch()

    assert [j.id for j in jobs] == ["workable:huggingface:a", "workable:huggingface:b"]
    assert route.call_count == 2
    first_body = json.loads(route.calls[0].request.content)
    second_body = json.loads(route.calls[1].request.content)
    assert "token" not in first_body  # no token on the first request
    assert second_body["token"] == "TOK2"  # token echoed back on the second


@respx.mock
async def test_fetch_stops_when_no_next_page() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"results": [posting()], "nextPage": None})
    )
    async with httpx.AsyncClient() as client:
        jobs = await WorkableSource("huggingface", client).fetch()
    assert len(jobs) == 1
    assert route.call_count == 1


@respx.mock
async def test_fetch_raises_on_http_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await WorkableSource("huggingface", client).fetch()

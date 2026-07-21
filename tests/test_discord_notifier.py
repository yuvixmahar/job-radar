import json

import httpx
import pytest
import respx

from jobradar.models import Job
from jobradar.notifiers.discord import DiscordNotifier

WEBHOOK = "https://discord.com/api/webhooks/123/abc"


def make_job(id: str = "1", title: str = "Backend Engineer") -> Job:
    return Job(id=id, source="s", company="Acme", title=title, url=f"https://x/{id}")


@respx.mock
async def test_send_posts_message_to_webhook() -> None:
    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(204))
    async with httpx.AsyncClient() as client:
        await DiscordNotifier(WEBHOOK, client).send([make_job(title="Backend Engineer")])

    assert route.called
    payload = json.loads(route.calls[0].request.content)
    assert "Backend Engineer" in payload["content"]


@respx.mock
async def test_send_does_nothing_for_empty_jobs() -> None:
    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(204))
    async with httpx.AsyncClient() as client:
        await DiscordNotifier(WEBHOOK, client).send([])
    assert not route.called


@respx.mock
async def test_send_raises_on_http_error() -> None:
    respx.post(WEBHOOK).mock(return_value=httpx.Response(400))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await DiscordNotifier(WEBHOOK, client).send([make_job()])

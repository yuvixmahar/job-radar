import json

import httpx
import pytest
import respx

from jobradar.models import Job
from jobradar.notifiers.telegram import TelegramNotifier

TOKEN = "123456:ABC-DEF"
CHAT_ID = "987654"
API = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def make_job(id: str = "1", title: str = "Backend Engineer") -> Job:
    return Job(id=id, source="s", company="Acme", title=title, url=f"https://x/{id}")


@respx.mock
async def test_send_posts_message_to_bot_api() -> None:
    route = respx.post(API).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient() as client:
        await TelegramNotifier(TOKEN, CHAT_ID, client).send([make_job(title="Backend Engineer")])

    assert route.called
    payload = json.loads(route.calls[0].request.content)
    assert payload["chat_id"] == CHAT_ID
    assert "Backend Engineer" in payload["text"]


@respx.mock
async def test_send_does_nothing_for_empty_jobs() -> None:
    route = respx.post(API).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient() as client:
        await TelegramNotifier(TOKEN, CHAT_ID, client).send([])
    assert not route.called


@respx.mock
async def test_send_raises_on_http_error() -> None:
    respx.post(API).mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await TelegramNotifier(TOKEN, CHAT_ID, client).send([make_job()])

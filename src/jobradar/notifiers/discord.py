"""Discord notifier — POST matched jobs to an incoming webhook URL.

Paste a channel webhook URL into config (``type: discord``, ``webhook_url: ...``);
no OAuth. The HTTP client is injected (shared, politely configured) like the
sources. Discord caps message ``content`` at 2000 characters.
"""

from typing import Any, Self

import httpx

from jobradar.models import Job
from jobradar.notifiers._format import build_message
from jobradar.notifiers.base import Notifier

_DISCORD_MAX = 2000


class DiscordNotifier(Notifier):
    """Deliver matched postings to a Discord channel via an incoming webhook."""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient) -> None:
        self._webhook_url = webhook_url
        self._client = client

    @classmethod
    def from_config(cls, settings: dict[str, Any], client: httpx.AsyncClient) -> Self:
        """Build from config; requires a ``webhook_url`` setting."""
        webhook_url = settings.get("webhook_url")
        if not webhook_url:
            raise ValueError("discord notifier requires 'webhook_url'")
        return cls(str(webhook_url), client)

    async def send(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        content = build_message(jobs, max_len=_DISCORD_MAX)
        response = await self._client.post(self._webhook_url, json={"content": content})
        response.raise_for_status()

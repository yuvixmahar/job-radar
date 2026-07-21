"""Telegram notifier — POST matched jobs via the Bot API ``sendMessage``.

Create a bot with @BotFather, put its token and your chat id in config
(``type: telegram``, ``bot_token: ...``, ``chat_id: ...``); no OAuth. The HTTP
client is injected. Telegram caps message ``text`` at 4096 characters.
"""

import httpx

from jobradar.models import Job
from jobradar.notifiers._format import build_message
from jobradar.notifiers.base import Notifier

_TELEGRAM_MAX = 4096


class TelegramNotifier(Notifier):
    """Deliver matched postings to a Telegram chat via a bot."""

    def __init__(self, bot_token: str, chat_id: str, client: httpx.AsyncClient) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._client = client

    async def send(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        text = build_message(jobs, max_len=_TELEGRAM_MAX)
        response = await self._client.post(self._url, json={"chat_id": self._chat_id, "text": text})
        response.raise_for_status()

"""The ``Notifier`` contract: deliver matched jobs to one channel.

Every delivery channel — console, Discord webhook, Telegram, Slack, later an
OAuth-based one — implements this single async method. The runner fans
notifications out concurrently (like fetching), so ``send`` is a coroutine. How a
concrete notifier is configured (webhook URL, bot token) is its own constructor's
business, not part of this contract.
"""

from abc import ABC, abstractmethod

from jobradar.models import Job


class Notifier(ABC):
    """A channel that delivers matched job postings."""

    @abstractmethod
    async def send(self, jobs: list[Job]) -> None:
        """Deliver the given (already matched, already new) jobs to the channel."""
        raise NotImplementedError

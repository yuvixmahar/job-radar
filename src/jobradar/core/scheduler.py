"""Run a poll repeatedly on a fixed interval until cancelled.

A deliberately small async loop rather than a full scheduler: JobRadar needs one
job (the poll) at one fixed interval, run until the user stops it. ``run_forever``
polls immediately, then every ``interval_seconds``. A poll that raises is logged
and the loop continues — one bad cycle shouldn't kill the watcher — but
cancellation (Ctrl+C / task cancellation) propagates so it can stop cleanly.

``sleep`` and ``max_iterations`` are injectable so tests run without real time.
"""

import asyncio
from collections.abc import Awaitable, Callable

import structlog

_log = structlog.get_logger("jobradar.scheduler")

Poll = Callable[[], Awaitable[object]]
Sleep = Callable[[float], Awaitable[object]]


async def run_forever(
    poll: Poll,
    interval_seconds: float,
    *,
    max_iterations: int | None = None,
    sleep: Sleep = asyncio.sleep,
) -> int:
    """Poll now, then every ``interval_seconds``; return the number of polls run.

    ``max_iterations`` stops the loop after N polls (``None`` = forever). A poll
    raising :class:`Exception` is logged and skipped; :class:`BaseException`
    (e.g. cancellation) propagates.
    """
    count = 0
    while True:
        try:
            await poll()
        except Exception as exc:
            _log.warning("poll_failed", error=str(exc))
        count += 1
        if max_iterations is not None and count >= max_iterations:
            return count
        await sleep(interval_seconds)

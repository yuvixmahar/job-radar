import asyncio

import pytest

from jobradar.core.scheduler import run_forever


async def test_runs_immediately_and_repeats() -> None:
    polls = 0
    sleeps: list[float] = []

    async def poll() -> None:
        nonlocal polls
        polls += 1

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    count = await run_forever(poll, 60.0, max_iterations=3, sleep=fake_sleep)

    assert count == 3
    assert polls == 3
    assert sleeps == [60.0, 60.0]  # sleeps between polls, not after the last


async def test_single_iteration_does_not_sleep() -> None:
    sleeps: list[float] = []

    async def poll() -> None:
        pass

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    count = await run_forever(poll, 5.0, max_iterations=1, sleep=fake_sleep)

    assert count == 1
    assert sleeps == []


async def test_failing_poll_is_logged_and_loop_continues() -> None:
    attempts = 0

    async def poll() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    async def fake_sleep(seconds: float) -> None:
        pass

    count = await run_forever(poll, 1.0, max_iterations=2, sleep=fake_sleep)

    assert count == 2  # kept going despite both polls raising
    assert attempts == 2


async def test_cancellation_propagates() -> None:
    async def poll() -> None:
        raise asyncio.CancelledError

    async def fake_sleep(seconds: float) -> None:
        pass

    with pytest.raises(asyncio.CancelledError):
        await run_forever(poll, 1.0, max_iterations=5, sleep=fake_sleep)

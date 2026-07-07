import inspect

import pytest

from jobradar.models import Job
from jobradar.notifiers.base import Notifier


def test_cannot_instantiate_the_abc() -> None:
    with pytest.raises(TypeError):
        Notifier()  # type: ignore[abstract]


def test_subclass_without_send_cannot_instantiate() -> None:
    class Incomplete(Notifier):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_send_is_a_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(Notifier.send)


async def test_concrete_notifier_receives_jobs() -> None:
    received: list[Job] = []

    class Recorder(Notifier):
        async def send(self, jobs: list[Job]) -> None:
            received.extend(jobs)

    job = Job(id="x:1", source="x", company="Acme", title="Engineer", url="u")
    await Recorder().send([job])
    assert received == [job]

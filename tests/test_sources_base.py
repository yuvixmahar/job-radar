import inspect

import pytest

from jobradar.models import Job
from jobradar.sources.base import JobSource


def test_cannot_instantiate_the_abc() -> None:
    with pytest.raises(TypeError):
        JobSource()  # type: ignore[abstract]


def test_subclass_without_fetch_cannot_instantiate() -> None:
    class Incomplete(JobSource):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_fetch_is_a_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(JobSource.fetch)


async def test_concrete_source_can_fetch() -> None:
    class StaticSource(JobSource):
        async def fetch(self) -> list[Job]:
            return [Job(id="x:1", source="x", company="Acme", title="Engineer", url="u")]

    jobs = await StaticSource().fetch()
    assert [j.id for j in jobs] == ["x:1"]

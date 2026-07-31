from jobradar.core.dedup import SeenStore
from jobradar.core.runner import Runner
from jobradar.models import Job, MatchRule
from jobradar.notifiers.base import Notifier
from jobradar.sources.base import JobSource


def make_job(id: str, title: str, location: str | None = None) -> Job:
    return Job(
        id=id, source="fake", company="Acme", title=title, url=f"https://x/{id}", location=location
    )


class FakeSource(JobSource):
    def __init__(self, jobs: list[Job], *, fail: bool = False) -> None:
        self._jobs = jobs
        self._fail = fail

    async def fetch(self) -> list[Job]:
        if self._fail:
            raise RuntimeError("source boom")
        return self._jobs


class RecordingNotifier(Notifier):
    def __init__(self, *, fail: bool = False) -> None:
        self.batches: list[list[Job]] = []
        self._fail = fail

    async def send(self, jobs: list[Job]) -> None:
        if self._fail:
            raise RuntimeError("notify boom")
        self.batches.append(list(jobs))


def runner(
    sources: list[JobSource],
    notifiers: list[Notifier],
    store: SeenStore,
    *,
    keywords: tuple[str, ...] = ("engineer",),
    locations: tuple[str, ...] = (),
) -> Runner:
    return Runner(
        sources,
        MatchRule(keywords=keywords),
        store,
        notifiers,
        location_rule=MatchRule(keywords=locations),
    )


async def test_matches_dedups_and_notifies() -> None:
    jobs = [make_job("1", "Backend Engineer"), make_job("2", "Product Manager")]
    source = FakeSource(jobs)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store).run_once()

    assert [j.id for j in new] == ["1"]  # only the matching title, not the PM
    assert notifier.batches == [[make_job("1", "Backend Engineer")]]


async def test_non_matching_jobs_are_filtered_out() -> None:
    source = FakeSource([make_job("1", "Product Manager")])
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store).run_once()

    assert new == []
    assert notifier.batches == []  # nothing new -> notifier not called


async def test_empty_keywords_matches_everything() -> None:
    jobs = [make_job("1", "Backend Engineer"), make_job("2", "Product Manager")]
    source = FakeSource(jobs)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store, keywords=()).run_once()

    assert {j.id for j in new} == {"1", "2"}


async def test_location_filter_ands_with_keywords() -> None:
    jobs = [
        make_job("1", "Backend Engineer", "Toronto, ON, Canada"),  # title + location
        make_job("2", "Backend Engineer", "Austin, TX"),  # title only
        make_job("3", "Product Manager", "Toronto, ON, Canada"),  # location only
    ]
    source = FakeSource(jobs)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store, locations=("Canada",)).run_once()

    assert [j.id for j in new] == ["1"]  # only the one passing BOTH filters


async def test_location_filter_drops_jobs_with_no_location() -> None:
    jobs = [
        make_job("1", "Backend Engineer", "Vancouver, BC, Canada"),
        make_job("2", "Backend Engineer", None),  # no location -> dropped
    ]
    source = FakeSource(jobs)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store, locations=("Canada",)).run_once()

    assert [j.id for j in new] == ["1"]


async def test_empty_location_rule_keeps_jobs_with_no_location() -> None:
    jobs = [make_job("1", "Backend Engineer", None), make_job("2", "Backend Engineer", "Anywhere")]
    source = FakeSource(jobs)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [notifier], store).run_once()  # no location filter

    assert {j.id for j in new} == {"1", "2"}


async def test_second_run_reports_no_new_jobs() -> None:
    source = FakeSource([make_job("1", "Backend Engineer")])
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        r = runner([source], [notifier], store)
        first = await r.run_once()
        second = await r.run_once()

    assert [j.id for j in first] == ["1"]
    assert second == []
    assert len(notifier.batches) == 1  # notified once, not twice


async def test_failing_source_does_not_sink_the_run() -> None:
    good = FakeSource([make_job("1", "Backend Engineer")])
    bad = FakeSource([], fail=True)
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([bad, good], [notifier], store).run_once()

    assert [j.id for j in new] == ["1"]  # good source still delivered


async def test_failing_notifier_does_not_block_others() -> None:
    source = FakeSource([make_job("1", "Backend Engineer")])
    broken = RecordingNotifier(fail=True)
    working = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([source], [broken, working], store).run_once()

    assert [j.id for j in new] == ["1"]
    assert working.batches == [[make_job("1", "Backend Engineer")]]


async def test_duplicate_ids_across_sources_collapse() -> None:
    a = FakeSource([make_job("1", "Backend Engineer")])
    b = FakeSource([make_job("1", "Backend Engineer")])  # same id
    notifier = RecordingNotifier()
    with SeenStore(":memory:") as store:
        new = await runner([a, b], [notifier], store).run_once()

    assert [j.id for j in new] == ["1"]  # collapsed to one

import io

from jobradar.models import Job
from jobradar.notifiers.console import ConsoleNotifier


def make_job(
    *,
    id: str = "workday:ciena:R-1",
    title: str = "Firmware Engineer",
    company: str = "Ciena",
    location: str | None = "Ottawa, Canada",
    url: str = "https://ciena.example/job/R-1",
) -> Job:
    return Job(id=id, source="workday", company=company, title=title, url=url, location=location)


async def test_send_writes_header_and_job_lines() -> None:
    stream = io.StringIO()
    await ConsoleNotifier(stream).send([make_job()])
    output = stream.getvalue()

    assert "1 new job(s):" in output
    assert "Firmware Engineer  (Ciena, Ottawa, Canada)" in output
    assert "https://ciena.example/job/R-1" in output


async def test_output_is_ascii_only() -> None:
    stream = io.StringIO()
    await ConsoleNotifier(stream).send([make_job()])
    output = stream.getvalue()

    output.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII slipped in


async def test_send_omits_location_when_absent() -> None:
    stream = io.StringIO()
    await ConsoleNotifier(stream).send([make_job(location=None)])
    output = stream.getvalue()

    assert "Firmware Engineer  (Ciena)" in output
    assert "Ottawa" not in output


async def test_send_lists_every_job() -> None:
    stream = io.StringIO()
    jobs = [
        make_job(id="a", title="Backend Engineer"),
        make_job(id="b", title="Frontend Engineer"),
    ]
    await ConsoleNotifier(stream).send(jobs)
    output = stream.getvalue()

    assert "2 new job(s):" in output
    assert "Backend Engineer" in output
    assert "Frontend Engineer" in output


async def test_send_writes_nothing_for_empty_list() -> None:
    stream = io.StringIO()
    await ConsoleNotifier(stream).send([])
    assert stream.getvalue() == ""

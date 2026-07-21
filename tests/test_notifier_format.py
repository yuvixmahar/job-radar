from jobradar.models import Job
from jobradar.notifiers._format import build_message


def make_job(id: str, title: str, *, location: str | None = "Remote") -> Job:
    return Job(
        id=id, source="s", company="Acme", title=title, url=f"https://x/{id}", location=location
    )


def test_message_has_header_and_job_details() -> None:
    msg = build_message([make_job("1", "Backend Engineer")], max_len=2000)
    assert msg.startswith("1 new job(s):")
    assert "Backend Engineer @ Acme (Remote)" in msg
    assert "https://x/1" in msg


def test_message_omits_location_when_absent() -> None:
    msg = build_message([make_job("1", "Backend Engineer", location=None)], max_len=2000)
    assert "Backend Engineer @ Acme" in msg
    assert "()" not in msg


def test_message_truncates_and_notes_overflow() -> None:
    jobs = [make_job(str(i), f"Engineer {i}") for i in range(100)]
    msg = build_message(jobs, max_len=200)

    assert len(msg) <= 200
    assert msg.startswith("100 new job(s):")
    assert "more" in msg  # overflow note present


def test_message_lists_all_when_they_fit() -> None:
    jobs = [make_job("1", "Backend Engineer"), make_job("2", "Frontend Engineer")]
    msg = build_message(jobs, max_len=2000)
    assert "Backend Engineer" in msg
    assert "Frontend Engineer" in msg
    assert "more" not in msg

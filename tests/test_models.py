from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from jobradar.models import Job, MatchRule


def make_job(
    *,
    id: str = "workday:ciena:R-1",
    source: str = "workday",
    company: str = "Ciena",
    title: str = "Firmware Engineer",
    url: str = "https://ciena.wd5.myworkdayjobs.com/careers/job/R-1",
    location: str | None = None,
    posted_at: datetime | None = None,
    raw: dict[str, Any] | None = None,
) -> Job:
    return Job(
        id=id,
        source=source,
        company=company,
        title=title,
        url=url,
        location=location,
        posted_at=posted_at,
        raw=raw,
    )


def test_make_id_namespaces_parts() -> None:
    assert Job.make_id("workday", "ciena", "R-12345") == "workday:ciena:R-12345"


def test_optional_fields_default_to_none() -> None:
    job = make_job()
    assert job.location is None
    assert job.posted_at is None
    assert job.raw is None


def test_is_frozen() -> None:
    job = make_job()
    with pytest.raises(ValidationError):
        job.title = "changed"


def test_rejects_empty_required_fields() -> None:
    with pytest.raises(ValidationError):
        make_job(id="")
    with pytest.raises(ValidationError):
        make_job(title="")


def test_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Job(
            id="workday:ciena:R-1",
            source="workday",
            company="Ciena",
            title="Firmware Engineer",
            url="https://x/y",
            unexpected="nope",  # type: ignore[call-arg]
        )


def test_equality_is_by_id_only() -> None:
    a = make_job(title="A", company="Ciena", raw={"k": "v"})
    b = make_job(title="B", company="Different", raw=None)
    assert a == b  # same id, despite every other field differing


def test_differing_ids_are_not_equal() -> None:
    assert make_job(id="workday:ciena:R-1") != make_job(id="workday:ciena:R-2")


def test_not_equal_to_non_job() -> None:
    assert make_job() != "workday:ciena:R-1"


def test_dedups_in_a_set_by_id() -> None:
    a = make_job(title="A")
    b = make_job(title="B")  # same id as a
    c = make_job(id="workday:ciena:R-2")
    assert len({a, b, c}) == 2


def test_raw_excluded_from_repr() -> None:
    assert "raw" not in repr(make_job(raw={"secret": "value"}))


def test_matchrule_defaults_to_empty() -> None:
    assert MatchRule().keywords == ()


def test_matchrule_preserves_case_and_strips() -> None:
    rule = MatchRule(keywords=("  Firmware  ", "C++", ".NET"))
    assert rule.keywords == ("Firmware", "C++", ".NET")


def test_matchrule_collapses_internal_whitespace() -> None:
    rule = MatchRule(keywords=("Machine\t Learning", "Data   Engineer"))
    assert rule.keywords == ("Machine Learning", "Data Engineer")


def test_matchrule_drops_empties() -> None:
    rule = MatchRule(keywords=("", "   ", "Go"))
    assert rule.keywords == ("Go",)


def test_matchrule_dedups_case_insensitively_first_wins() -> None:
    rule = MatchRule(keywords=("Go", "rust", "GO", " go "))
    assert rule.keywords == ("Go", "rust")


def test_matchrule_accepts_a_list_at_runtime() -> None:
    # YAML/config produces lists; Pydantic coerces them to the stored tuple.
    rule = MatchRule.model_validate({"keywords": ["Go", "Rust"]})
    assert rule.keywords == ("Go", "Rust")


def test_matchrule_is_frozen() -> None:
    rule = MatchRule(keywords=("go",))
    with pytest.raises(ValidationError):
        rule.keywords = ("rust",)


def test_matchrule_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MatchRule(keywords=("go",), scope="title")  # type: ignore[call-arg]


def test_matchrule_rejects_non_sequence() -> None:
    with pytest.raises(ValidationError):
        MatchRule.model_validate({"keywords": "go"})


def test_matchrule_rejects_non_string_items() -> None:
    with pytest.raises(ValidationError):
        MatchRule.model_validate({"keywords": [1]})

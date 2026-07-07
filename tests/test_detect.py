import httpx
import pytest

from jobradar.core.detect import build_source, detect_ats
from jobradar.sources.greenhouse import GreenhouseSource
from jobradar.sources.workday import WorkdaySource


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://ciena.wd5.myworkdayjobs.com/Careers", "workday"),
        ("https://boards.greenhouse.io/acme", "greenhouse"),
        ("https://jobs.lever.co/acme", "lever"),
        ("https://jobs.ashbyhq.com/acme", "ashby"),
        ("https://careers-acme.icims.com/jobs", "icims"),
        ("https://careers.smartrecruiters.com/acme", "smartrecruiters"),
    ],
)
def test_detect_ats_identifies_known_hosts(url: str, key: str) -> None:
    assert detect_ats(url) == key


@pytest.mark.parametrize(
    "url",
    [
        "https://careers.example.com/jobs",
        "https://example.org",
        "not-a-url",
    ],
)
def test_detect_ats_returns_none_for_unknown(url: str) -> None:
    assert detect_ats(url) is None


def test_detect_ats_matches_bare_domain_and_subdomain() -> None:
    assert detect_ats("https://greenhouse.io/x") == "greenhouse"
    assert detect_ats("https://boards.greenhouse.io/x") == "greenhouse"


def test_detect_ats_does_not_false_match_lookalike_host() -> None:
    assert detect_ats("https://notgreenhouse.io/x") is None


async def test_build_source_returns_workday_adapter() -> None:
    async with httpx.AsyncClient() as client:
        source = build_source("https://ciena.wd5.myworkdayjobs.com/Careers", client)
    assert isinstance(source, WorkdaySource)


async def test_build_source_returns_greenhouse_adapter() -> None:
    async with httpx.AsyncClient() as client:
        source = build_source("https://boards.greenhouse.io/acme", client)
    assert isinstance(source, GreenhouseSource)


async def test_build_source_rejects_unknown_ats() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            build_source("https://careers.example.com/jobs", client)


async def test_build_source_detected_but_no_adapter_yet() -> None:
    # Lever is fingerprinted but has no adapter yet.
    async with httpx.AsyncClient() as client:
        with pytest.raises(NotImplementedError):
            build_source("https://jobs.lever.co/acme", client)

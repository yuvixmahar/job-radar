from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from jobradar.cli import app
from jobradar.config import CompanyConfig, Config, NotifierConfig
from jobradar.core.scheduler import Poll

runner = CliRunner()

GH_ENDPOINT = "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs"


def gh_posting(*, id: int = 1, title: str = "Backend Engineer") -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "absolute_url": f"https://boards.greenhouse.io/airbnb/jobs/{id}",
        "location": {"name": "Remote"},
        "updated_at": "2024-01-01T00:00:00Z",
    }


# --- add-company ---


def test_add_company_appends_to_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    result = runner.invoke(
        app, ["add-company", "https://boards.greenhouse.io/airbnb", "--config", str(cfg_path)]
    )
    assert result.exit_code == 0, result.output
    assert "greenhouse" in result.output.lower()

    config = Config.load(cfg_path)
    assert [c.url for c in config.companies] == ["https://boards.greenhouse.io/airbnb"]


def test_add_company_stores_display_name(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    result = runner.invoke(
        app,
        [
            "add-company",
            "https://jobs.lever.co/acme",
            "--company",
            "Acme Corp",
            "--config",
            str(cfg_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert Config.load(cfg_path).companies[0].company == "Acme Corp"


def test_add_company_is_idempotent(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    args = ["add-company", "https://boards.greenhouse.io/airbnb", "--config", str(cfg_path)]
    runner.invoke(app, args)
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert "already watching" in result.output.lower()
    assert len(Config.load(cfg_path).companies) == 1


def test_add_company_rejects_unknown_ats(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    result = runner.invoke(
        app, ["add-company", "https://careers.example.com/jobs", "--config", str(cfg_path)]
    )
    assert result.exit_code == 1
    assert not cfg_path.exists()  # nothing written on failure


# --- list ---


def test_list_shows_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    Config(
        keywords=("engineer",),
        companies=(CompanyConfig(url="https://boards.greenhouse.io/airbnb", company="Airbnb"),),
    ).save(cfg_path)
    result = runner.invoke(app, ["list", "--config", str(cfg_path)])
    assert result.exit_code == 0
    assert "engineer" in result.output.lower()
    assert "airbnb" in result.output.lower()


# --- run ---


def test_run_without_companies_errors(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    Config().save(cfg_path)
    result = runner.invoke(app, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 1


@respx.mock
def test_run_end_to_end_prints_matches(tmp_path: Path) -> None:
    jobs = [gh_posting(title="Backend Engineer"), gh_posting(id=2, title="Designer")]
    respx.get(GH_ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": jobs}))
    cfg_path = tmp_path / "config.yaml"
    Config(
        keywords=("engineer",),
        companies=(CompanyConfig(url="https://boards.greenhouse.io/airbnb"),),
        notifiers=(NotifierConfig(type="console"),),
    ).save(cfg_path)

    result = runner.invoke(app, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "Backend Engineer" in result.output
    assert "Designer" not in result.output  # filtered out by keyword


@respx.mock
def test_run_second_time_reports_no_new_jobs(tmp_path: Path) -> None:
    respx.get(GH_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"jobs": [gh_posting(title="Backend Engineer")]})
    )
    cfg_path = tmp_path / "config.yaml"
    Config(
        keywords=("engineer",),
        companies=(CompanyConfig(url="https://boards.greenhouse.io/airbnb"),),
    ).save(cfg_path)

    runner.invoke(app, ["run", "--config", str(cfg_path)])  # first: notifies
    result = runner.invoke(app, ["run", "--config", str(cfg_path)])  # second: deduped
    assert result.exit_code == 0, result.output
    assert "No new matching jobs." in result.output


def test_run_watch_schedules_on_configured_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / "config.yaml"
    Config(
        poll_interval_minutes=15,
        companies=(CompanyConfig(url="https://boards.greenhouse.io/airbnb"),),
    ).save(cfg_path)

    seen: dict[str, float] = {}

    async def fake_run_forever(poll: Poll, interval_seconds: float) -> int:
        seen["interval"] = interval_seconds  # capture, don't actually loop
        return 0

    monkeypatch.setattr("jobradar.cli.run_forever", fake_run_forever)

    result = runner.invoke(app, ["run", "--watch", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "Watching" in result.output
    assert seen["interval"] == 15 * 60  # minutes -> seconds

from pathlib import Path

import pytest
from pydantic import ValidationError

from jobradar.config import CompanyConfig, Config, NotifierConfig


def test_defaults() -> None:
    cfg = Config()
    assert cfg.keywords == ()
    assert cfg.poll_interval_minutes == 30
    assert cfg.companies == ()
    assert len(cfg.notifiers) == 1
    assert cfg.notifiers[0].type == "console"


def test_load_missing_file_yields_defaults(tmp_path: Path) -> None:
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg == Config()


def test_load_empty_file_yields_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    assert Config.load(path) == Config()


def test_load_parses_hand_written_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
keywords: [engineer, python]
poll_interval_minutes: 15
companies:
  - url: https://boards.greenhouse.io/airbnb
    company: Airbnb
notifiers:
  - type: discord
    webhook_url: https://discord.example/webhook
""",
        encoding="utf-8",
    )
    cfg = Config.load(path)

    assert cfg.keywords == ("engineer", "python")
    assert cfg.poll_interval_minutes == 15
    assert cfg.companies[0].url == "https://boards.greenhouse.io/airbnb"
    assert cfg.companies[0].company == "Airbnb"
    assert cfg.notifiers[0].type == "discord"
    extra = cfg.notifiers[0].model_extra
    assert extra is not None
    assert extra["webhook_url"] == "https://discord.example/webhook"


def test_save_then_load_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    original = Config(
        keywords=("engineer", "C++"),
        poll_interval_minutes=45,
        companies=(CompanyConfig(url="https://x/y", company="X"),),
        notifiers=(NotifierConfig(type="console"),),
    )
    original.save(path)
    assert Config.load(path) == original


def test_save_preserves_notifier_extras(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    slack = NotifierConfig.model_validate({"type": "slack", "webhook_url": "https://s/w"})
    Config(notifiers=(slack,)).save(path)
    reloaded = Config.load(path)
    extra = reloaded.notifiers[0].model_extra
    assert extra is not None
    assert extra["webhook_url"] == "https://s/w"


def test_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("kewords: [typo]\n", encoding="utf-8")  # misspelled
    with pytest.raises(ValidationError):
        Config.load(path)


def test_rejects_non_positive_interval() -> None:
    with pytest.raises(ValidationError):
        Config(poll_interval_minutes=0)


def test_company_requires_url() -> None:
    with pytest.raises(ValidationError):
        CompanyConfig(company="X")  # type: ignore[call-arg]

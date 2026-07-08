"""Config schema for the hand-editable ``config.yaml`` (also written by the CLI).

The YAML is the source of truth *and* human-editable: users hand-edit keywords
and notifier settings, while ``jobradar add-company`` appends to ``companies``.
This module is just the schema plus :meth:`Config.load` / :meth:`Config.save` —
building live sources/notifiers/runner from it happens in the CLI layer.

A plain Pydantic ``BaseModel`` (not ``BaseSettings``) so we can both read and
*write* the file; ``extra="forbid"`` on the top level surfaces typos in
hand-edited YAML instead of silently ignoring them.
"""

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field


class CompanyConfig(BaseModel):
    """One watched company: a careers URL, optional display name."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    company: str | None = None


class NotifierConfig(BaseModel):
    """One notifier: a ``type`` plus channel-specific settings (webhook_url, …).

    ``extra="allow"`` keeps per-type settings (e.g. a Discord ``webhook_url``) so
    they round-trip through save/load; the CLI's notifier factory reads them.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1)


class Config(BaseModel):
    """Top-level JobRadar configuration."""

    model_config = ConfigDict(extra="forbid")

    keywords: tuple[str, ...] = ()
    poll_interval_minutes: int = Field(default=30, gt=0)
    companies: tuple[CompanyConfig, ...] = ()
    notifiers: tuple[NotifierConfig, ...] = Field(
        default_factory=lambda: (NotifierConfig(type="console"),)
    )

    @classmethod
    def load(cls, path: Path) -> Self:
        """Load config from YAML; a missing file yields default config."""
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        """Write config to YAML.

        ``mode="json"`` so tuples serialize as lists; ``exclude_none`` keeps the
        file tidy (e.g. no ``company: null`` for companies without a display name).
        """
        data = self.model_dump(mode="json", exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

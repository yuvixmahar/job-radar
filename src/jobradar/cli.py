"""Command-line front door: ``add-company``, ``list``, ``run``.

The CLI is a thin layer over the config + detection + runner pieces. It reads and
writes the same human-editable ``config.yaml`` (the hybrid model): ``add-company``
detects the ATS and appends to it, ``list`` shows it, ``run`` builds the live
sources/notifiers/store and polls once (or continuously with ``--watch``).
"""

import asyncio
from pathlib import Path
from typing import Annotated, NoReturn

import httpx
import typer

from jobradar.config import CompanyConfig, Config
from jobradar.core.dedup import SeenStore
from jobradar.core.detect import build_source, check_supported
from jobradar.core.runner import Runner
from jobradar.core.scheduler import run_forever
from jobradar.models import MatchRule
from jobradar.notifiers.base import Notifier
from jobradar.notifiers.console import ConsoleNotifier
from jobradar.notifiers.discord import DiscordNotifier
from jobradar.notifiers.telegram import TelegramNotifier

app = typer.Typer(
    help="Watch career sites for new job postings matching your keywords.",
    no_args_is_help=True,
    add_completion=False,
)

_USER_AGENT = "JobRadar/0.1 (+https://github.com/yuvixmahar/job-radar)"

ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml")]
_DEFAULT_CONFIG = Path("config.yaml")


def _db_path(config_path: Path) -> Path:
    """Store the dedup DB next to the config file."""
    return config_path.with_name("jobradar.db")


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _build_notifiers(config: Config, client: httpx.AsyncClient) -> list[Notifier]:
    """Build notifier instances from config, reading webhook settings from extras."""
    notifiers: list[Notifier] = []
    for entry in config.notifiers:
        extra = entry.model_extra or {}
        if entry.type == "console":
            notifiers.append(ConsoleNotifier())
        elif entry.type == "discord":
            webhook_url = extra.get("webhook_url")
            if not webhook_url:
                _fail("discord notifier requires 'webhook_url'")
            notifiers.append(DiscordNotifier(str(webhook_url), client))
        elif entry.type == "telegram":
            token, chat_id = extra.get("bot_token"), extra.get("chat_id")
            if not token or chat_id is None:
                _fail("telegram notifier requires 'bot_token' and 'chat_id'")
            notifiers.append(TelegramNotifier(str(token), str(chat_id), client))
        else:
            _fail(f"unknown notifier type {entry.type!r}")
    return notifiers


@app.command("add-company")
def add_company(
    url: Annotated[str, typer.Argument(help="Careers page URL")],
    company: Annotated[str | None, typer.Option(help="Display name (optional)")] = None,
    config_path: ConfigOpt = _DEFAULT_CONFIG,
) -> None:
    """Detect the ATS for a careers URL and add it to the config."""
    try:
        key = check_supported(url)
    except (ValueError, NotImplementedError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    config = Config.load(config_path)
    if any(existing.url == url for existing in config.companies):
        typer.echo(f"Already watching {url}")
        return

    updated = config.model_copy(
        update={"companies": (*config.companies, CompanyConfig(url=url, company=company))}
    )
    updated.save(config_path)
    typer.echo(f"Added {key} company: {url}")


@app.command("list")
def list_config(config_path: ConfigOpt = _DEFAULT_CONFIG) -> None:
    """Show the current configuration."""
    config = Config.load(config_path)
    keywords = ", ".join(config.keywords) if config.keywords else "(none - watching all)"
    typer.echo(f"Config:    {config_path}")
    typer.echo(f"Keywords:  {keywords}")
    typer.echo(f"Interval:  {config.poll_interval_minutes} min")
    typer.echo(f"Notifiers: {', '.join(n.type for n in config.notifiers)}")
    typer.echo("Companies:")
    if not config.companies:
        typer.echo("  (none — add one with 'jobradar add-company <url>')")
    for entry in config.companies:
        name = f"  ({entry.company})" if entry.company else ""
        typer.echo(f"  - {entry.url}{name}")


@app.command("run")
def run(
    config_path: ConfigOpt = _DEFAULT_CONFIG,
    watch: Annotated[
        bool,
        typer.Option("--watch", "-w", help="Poll continuously on the configured interval."),
    ] = False,
) -> None:
    """Poll once (default) or continuously with --watch: fetch, match, dedup, notify."""
    config = Config.load(config_path)
    if not config.companies:
        typer.echo("No companies configured. Add one with 'jobradar add-company <url>'.", err=True)
        raise typer.Exit(1)

    for entry in config.companies:  # validate URLs up front (no network)
        try:
            check_supported(entry.url)
        except (ValueError, NotImplementedError) as exc:
            typer.echo(f"Error for {entry.url}: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        asyncio.run(_run(config, _db_path(config_path), watch=watch))
    except KeyboardInterrupt:
        typer.echo("\nStopped.")


async def _run(config: Config, db_path: Path, *, watch: bool) -> None:
    rule = MatchRule(keywords=config.keywords)
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    ) as client:
        notifiers = _build_notifiers(config, client)
        sources = [build_source(c.url, client, company=c.company) for c in config.companies]
        with SeenStore(db_path) as store:
            runner = Runner(sources, rule, store, notifiers)
            if not watch:
                new_jobs = await runner.run_once()
                if not new_jobs:
                    typer.echo("No new matching jobs.")
                return
            interval = config.poll_interval_minutes
            typer.echo(
                f"Watching {len(sources)} company(ies) every {interval} min. Press Ctrl+C to stop."
            )
            await run_forever(runner.run_once, interval * 60)

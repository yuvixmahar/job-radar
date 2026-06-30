# JobRadar

Watch company career sites for new job postings matching your keywords, and get
notified the moment a match appears.

JobRadar polls Applicant Tracking Systems (ATS) directly — Workday, iCIMS,
Greenhouse, Lever, Ashby, SmartRecruiters — so alerts are fresh and accurate
rather than lagging behind a third-party aggregator. You point it at a careers
URL; it fingerprints the ATS automatically, normalizes every posting, dedupes
against what it has already seen, and pushes new matches to the channels you
configure.

> Status: **early development.** APIs and config format may change.

## Why direct ATS adapters

- **Freshness.** Aggregators lag by hours or days; for a "new posting" alert
  that is disqualifying. Direct adapters see a role as soon as it is public.
- **One adapter per platform, not per company.** A single `WorkdaySource`
  covers every Workday tenant (thousands of companies). Cover ~6 platforms and
  you have most of the tech/corporate market.
- **Auto-detection.** `jobradar add-company <careers-url>` fingerprints the ATS
  from the URL (and, if needed, by following redirects / scanning the page) —
  you never pick an adapter by hand.

## Architecture at a glance

Two abstractions, everything else is a swappable plugin:

- **`JobSource`** — `fetch()` returns normalized `Job` objects. One adapter per
  ATS platform.
- **`Notifier`** — `send(jobs)` delivers matches to a channel.

Plugins are registered via Python entry points (`jobradar.sources`,
`jobradar.notifiers`), so third parties can ship sources/notifiers in their own
package without touching core code.

The `run()` pipeline: concurrent fetch (`asyncio.gather`, capped by a
`Semaphore`) → flatten → load known IDs into a set → filter new in memory →
batch `INSERT OR IGNORE` into SQLite → notify concurrently on new jobs only.

## Planned sources & notifiers

| Sources (ATS)                                                  | Notifiers                                  |
| ------------------------------------------------------------- | ------------------------------------------ |
| Workday, iCIMS, Greenhouse, Lever, Ashby, SmartRecruiters     | Console, Discord, Telegram, Slack webhook  |
| Adzuna (aggregator — designed-for, not yet implemented)       | OAuth notifiers (Slack/Gmail/Discord, later) |

## Tech stack

Typer (CLI) · Pydantic v2 + pydantic-settings · httpx (async) · SQLite (stdlib)
· APScheduler · structlog · pytest + respx · ruff + mypy.

## Development

This project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.11+.

```bash
uv sync                 # create venv + install deps (incl. dev group)
uv run pytest           # run tests
uv run ruff check .     # lint
uv run mypy             # type-check
```

## License

[MIT](LICENSE)

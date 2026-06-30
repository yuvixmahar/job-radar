# CLAUDE.md — JobRadar working rules

Rules and architectural decisions for working in this repo. Read fully before
writing code. These decisions are deliberate; do not silently revert them.

## What this project is

A Python tool that watches company career sites (ATS platforms) for new job
postings matching the user's keywords and sends notifications when new matches
appear. It is both a personal automation tool **and a portfolio piece** —
clean abstractions, full typing, and tests matter as much as functionality.
Build it to be genuinely useful to other developers, not a toy.

## Non-negotiable architecture decisions

These were decided with reasoning. Honor them. If you believe one is wrong,
raise it explicitly — do not quietly change it.

1. **Two ABCs, everything else is a plugin.**
   - `JobSource.fetch()` → `list[Job]` (normalized). **One adapter per ATS
     platform, never per company.**
   - `Notifier.send(jobs)` → delivers matches to a channel.
   - Plugins register via entry points (`jobradar.sources`,
     `jobradar.notifiers`) in `pyproject.toml`; load with
     `importlib.metadata.entry_points()`. Third parties must be able to add a
     source/notifier from their own package without editing core.

2. **Extraction = one adapter per ATS, with rules-based auto-detection.**
   - Adapters: Workday, iCIMS, Greenhouse, Lever, Ashby, SmartRecruiters.
   - `WorkdaySource(tenant, datacenter, site)` covers every Workday tenant via
     `POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
     with body `{"limit":20,"offset":0,"searchText":"","appliedFacets":{}}`,
     paginated JSON.
   - iCIMS is HTML (selectolax/lxml), `pr` pagination param. Greenhouse/Lever/
     Ashby/SmartRecruiters have clean public APIs.
   - **Auto-detect, never make the user pick an adapter.** Fingerprint the ATS
     from the careers URL host (`myworkdayjobs.com`→workday, `icims.com`→icims,
     …). For custom domains, follow redirects and check the final host, then
     fall back to fetching the HTML once and regex-scanning for known ATS
     markers. A registry maps detected ATS key → adapter class + URL parser.
     UX is just `jobradar add-company <careers-url>`.
   - This is **pure rules, no AI** (covers ~80–90%). An optional LLM
     "classify this unknown page" step is a **fallback only, never the core.**

3. **Adzuna (aggregator) is a parallel `JobSource`, not a replacement.**
   - Direct ATS adapters are the source of truth for watched companies (max
     freshness). Adzuna = wide net for discovery + fallback for ATSs without an
     adapter yet. Both flow through the same matcher and dedup.
   - **This version: design for it, leave room, do NOT implement it.** No deep
     research needed now. Verify Adzuna's free-tier limits/licensing before
     anything depends on it.

4. **Concurrency: async for I/O, sync for the DB.**
   - Fetch all sources concurrently with `asyncio.gather(..., return_exceptions=True)`
     so one flaky source can't sink the run; cap with a `Semaphore` to stay
     polite per-host. Fan out notifications concurrently too.
   - **Do NOT make the database async.** SQLite is in-process; aiosqlite just
     thread-pools it and the thread-hop costs more than it saves for
     microsecond lookups. Decided against deliberately.

5. **Dedup: in-memory `set` + SQLite as the set. No list/binary search.**
   - Binary search's O(n) array-shift inserts are exactly the write cost to
     avoid. `id TEXT PRIMARY KEY`; batch `INSERT OR IGNORE` in one transaction;
     B-tree dedups at O(log n). Pre-filter against an in-memory set (loaded
     once) to know which rows are genuinely new → notify only on those.
   - The whole `run()`: concurrent fetch → flatten → load known IDs into a set
     → filter new in memory → batch `INSERT OR IGNORE` → concurrent notify on
     new only. **Two DB queries per poll regardless of job count.**

6. **Notifiers: webhook/token first, OAuth later.**
   - First: console, Discord webhook, Telegram bot, Slack incoming webhook
     (paste URL/token into config). **These must work before any OAuth.**
   - Later: an `OAuthNotifier` base (authorize→exchange→store→refresh) via
     `authlib`, tiny local callback server at `http://localhost:8765/callback`.
     Tokens stored **encrypted (keyring/Fernet), never in YAML.** OAuth must not
     block the MVP.

## Build order

Work in this order; prioritize clean abstractions + tests over breadth.

1. `models.py` (`Job`, `MatchRule`), `core/matcher.py`, `core/dedup.py`
   (set + `INSERT OR IGNORE`) — **with tests.**
2. `sources/base.py` (`JobSource` ABC) + `WorkdaySource` — URL parser,
   pagination, **respx-mocked tests.**
3. Detection registry (`core/detect.py`), remaining ATS adapters.
4. `notifiers/base.py` + console/Discord/Telegram/Slack, `core/runner.py`,
   `core/scheduler.py`, `cli.py`, config.
5. OAuth notifiers; design space for Adzuna.

## Code standards

- **Full type hints** on everything; code must pass `mypy --strict` (configured
  in `pyproject.toml`). Ship a `py.typed` marker (present).
- **Lint/format with ruff** (config in `pyproject.toml`). Keep it clean.
- **Tests with pytest; mock all HTTP with `respx`** — tests must never hit the
  network. `pytest-asyncio` for async (`asyncio_mode = "auto"`).
- Pydantic v2 models for `Job`/config; pydantic-settings + YAML for config.
- Structured logging via `structlog`. No bare `print` in library code (the
  console *notifier* is the exception — that's its job).
- Prefer `pathlib` over `os.path`; raise specific exceptions, not bare
  `Exception`.
- Be a polite scraper: realistic User-Agent, respect the `Semaphore` cap,
  sensible timeouts/retries. Don't hammer hosts in tests or real runs.

## Tooling & environment

- **Package manager: uv. Target Python 3.11+.** Use `uv add` / `uv add --dev`
  to manage deps (keeps `pyproject.toml` + `uv.lock` in sync); run via
  `uv run …`. Don't hand-edit dependency lists if `uv add` can do it.
- Common commands: `uv sync`, `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format`, `uv run mypy`.
- Windows dev host (PowerShell primary). Keep everything cross-platform — no
  POSIX-only assumptions, use `pathlib`.

## Git & commits

- **Conventional Commits** (`feat:`, `fix:`, `test:`, `refactor:`, `chore:`,
  `docs:`, `ci:`). Scope when useful, e.g. `feat(sources): add WorkdaySource`.
- **Commit per real unit of work** — don't pad commit count, don't lump
  unrelated changes. A unit usually = code + its tests passing.
- **Never add a `Co-Authored-By:` / co-author trailer** to commit messages.
- Don't commit secrets, tokens, `config.yaml`, or `*.db` (see `.gitignore`).
- Run lint + type-check + tests green before committing.

## Definition of done for a unit of work

`uv run ruff check .` clean · `uv run mypy` clean · `uv run pytest` green ·
new behavior covered by tests · committed with a Conventional Commit message.

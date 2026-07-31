# JobRadar

[![CI](https://github.com/yuvixmahar/job-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/yuvixmahar/job-radar/actions/workflows/ci.yml)

Watch company career sites for new job postings that match your keywords, and get
told about them as soon as they appear.

Most job alerts come from aggregators, which means you hear about a role hours or
days after it went live. JobRadar skips the middleman and talks to the system the
company actually posts through, so a listing shows up about as fast as it does on
the careers page itself.

You give it a careers URL. It works out which platform the company posts through,
pulls the postings, filters them by your keywords, remembers what it has already
shown you, and sends the new ones to your console, Discord, or Telegram.

> Status: early development, but the full pipeline works today. Config format may
> still change.

## Quick start

```bash
uv sync
uv run jobradar add-company https://boards.greenhouse.io/airbnb
uv run jobradar run
```

That is enough to get output. To keep it running in the background, use
`uv run jobradar run --watch`, which polls on the interval in your config until
you stop it.

Commands:

| Command | What it does |
| --- | --- |
| `jobradar add-company <url>` | Detects the platform behind a careers URL and adds it to your config |
| `jobradar list` | Shows what you are currently watching |
| `jobradar run` | Runs one poll |
| `jobradar run --watch` | Polls continuously on your configured interval |

`add-company` takes an optional `--company "Display Name"`, and every command
takes `--config / -c` to point at a config file other than `./config.yaml`.

## Configuration

Everything lives in a `config.yaml` that you can read and edit by hand. The CLI
writes to the same file, so you can use whichever is more convenient.

```yaml
keywords: [engineer, "C++", python]
poll_interval_minutes: 30

companies:
  - url: https://ciena.wd5.myworkdayjobs.com/Careers
    company: Ciena
  - url: https://boards.greenhouse.io/airbnb

notifiers:
  - type: console
  - type: discord
    webhook_url: https://discord.com/api/webhooks/...
```

Leave `keywords` empty and it watches every posting instead of filtering. A
Telegram notifier looks like `type: telegram` with `bot_token` and `chat_id`.

## What is interesting about it

**One adapter per platform, not per company.** A single `WorkdaySource` covers
every company hosted on Workday, which is thousands of them. A handful of adapters
therefore reaches a large share of tech and corporate employers, and adding a
company you want to watch is a line of config, not code.

**You never choose an adapter.** Paste a careers URL and the detection layer
fingerprints the platform from the host, then hands back the right adapter already
configured. `boards.greenhouse.io/airbnb` becomes a Greenhouse source pointed at
the `airbnb` board without you knowing Greenhouse has an API.

**Two interfaces, everything else is a plugin.** There are exactly two abstract
base classes: `JobSource.fetch()` returns normalized `Job` objects, and
`Notifier.send(jobs)` delivers them. Every source and every notifier is a small
module behind one of those two, and the matcher, deduplicator, and scheduler never
learn which platform a posting came from. The registries are loaded from Python
entry points (`jobradar.sources`, `jobradar.notifiers`), and each source declares
the URL hosts it handles, so a third party can ship a new adapter from their own
package and have `add-company` recognize its URLs without editing this codebase.

**Keyword matching that understands code.** Matching runs against the job title,
and searching for `C` should match "Embedded C Developer" but not "C++ Developer"
and not "Calculus". Plain substring search gets this wrong, and so do normal word
boundaries, because regex treats `+` and `#` as punctuation. The matcher builds a
per-keyword pattern that counts `+ # .` as part of a token, so `C`, `C++`, `C#`,
and `.NET` stay distinct.

**Deduplication costs two queries per poll, no matter the size.** Job IDs live in
SQLite with the ID as the primary key. Each poll reads the known IDs into a set,
filters in memory, then does one batched `INSERT OR IGNORE`. Whether a company
posts 5 roles or 5,000, that is still two round trips to the database.

**One flaky source cannot take down a run.** Sources are fetched concurrently with
a semaphore keeping the request rate polite. Failures are collected rather than
raised, so a company having a bad day gets logged and skipped while everything
else still reports. Notifications fan out the same way.

## Project layout

```
src/jobradar/
├── models.py        Job and MatchRule, the two value objects everything shares
├── config.py        The config.yaml schema, plus load and save
├── cli.py           The Typer commands, and the wiring that builds a live run
├── core/            The engine
│   ├── detect.py    Careers URL to platform to the right adapter (by host)
│   ├── matcher.py   Word boundary aware keyword matching, on the job title
│   ├── dedup.py     SQLite backed set of postings already seen
│   ├── runner.py    One poll: fetch, match, dedup, notify
│   └── scheduler.py Repeats a poll on a fixed interval
├── sources/         Getting postings in (one file per platform)
│   ├── base.py            The JobSource contract
│   ├── workday.py         Paginated JSON API, covers every Workday tenant
│   ├── greenhouse.py      Board API
│   ├── lever.py           Postings API
│   ├── ashby.py           Job board API
│   ├── smartrecruiters.py Postings API, offset paginated
│   ├── recruitee.py       Offers API (company slug is the subdomain)
│   ├── breezy.py          Public JSON board
│   ├── workable.py        POST API, token paginated
│   └── amazon.py          Amazon's own global jobs search
└── notifiers/       Sending matches out
    ├── base.py      The Notifier contract
    ├── console.py
    ├── discord.py
    └── telegram.py
```

The two `base.py` files are the whole architecture in miniature. `JobSource.fetch()`
returns normalized `Job` objects, `Notifier.send(jobs)` delivers them, and every
concrete source or notifier is a plugin behind one of those two interfaces.

## Supported today

Sources (9): Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee,
Breezy, Workable, and Amazon's own jobs board.

Notifiers (3): console, Discord, Telegram.

Detection also recognizes iCIMS URLs, but that adapter is not written yet, so
JobRadar tells you the platform is known but unimplemented rather than guessing.
Detection reads the URL host only, so a company on a custom vanity domain that
redirects to an ATS is not resolved yet.

## Not yet

On the roadmap: an iCIMS adapter, Slack and OAuth based notifiers, an Adzuna
aggregator source, and redirect-following in detection (so vanity domains
resolve).

## Tech stack

Requires Python 3.11 or newer, managed with [uv](https://docs.astral.sh/uv/).
Typer for the CLI, Pydantic v2 for models and config, httpx for async HTTP, SQLite
from the standard library, structlog for structured logs. Tested with pytest and
respx, checked with ruff and mypy in strict mode.

Continuous integration runs the lint, format, type check, and test steps on
Python 3.11, 3.12, 3.13, and 3.14, so the 3.11+ support is checked on every push
rather than just claimed.

## Development

```bash
uv sync                 # create the venv and install everything
uv run pytest           # tests
uv run ruff check .     # lint
uv run mypy             # type check
```

The suite is more than 200 tests, and every HTTP call is mocked, so nothing hits
the network.

## License

[MIT](LICENSE)

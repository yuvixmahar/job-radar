# JobRadar

Watch company career sites for new job postings that match your keywords, and get
told about them as soon as they appear.

Most job alerts come from aggregators, which means you hear about a role hours or
days after it went live. JobRadar skips the middleman and talks to the Applicant
Tracking System (ATS) that the company actually posts to, so a listing shows up
about as fast as it does on the careers page itself.

You give it a careers URL. It works out which ATS the company uses, pulls the
postings, filters them by your keywords, remembers what it has already shown you,
and sends the new ones to your console, Discord, or Telegram.

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
| `jobradar add-company <url>` | Detects the ATS behind a careers URL and adds it to your config |
| `jobradar list` | Shows what you are currently watching |
| `jobradar run` | Runs one poll |
| `jobradar run --watch` | Polls continuously on your configured interval |

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

Leave `keywords` empty and it watches every posting instead of filtering.

## What is interesting about it

**One adapter per ATS platform, not per company.** A single `WorkdaySource`
covers every company hosted on Workday, which is thousands of them. Support six
platforms and you have covered most of the corporate and tech market. Adding a
company is a config line, not code.

**You never choose an adapter.** Paste any careers URL and the detection layer
fingerprints the ATS from the hostname, then hands back the right adapter already
configured. `boards.greenhouse.io/airbnb` becomes a Greenhouse source pointed at
the `airbnb` board without you knowing Greenhouse has an API.

**Keyword matching that understands code.** Searching for `C` should match
"Embedded C Developer" but not "C++ Developer" and not "Calculus". Plain substring
search gets this wrong, and so do normal word boundaries, because regex treats `+`
and `#` as punctuation. The matcher builds a per-keyword pattern that counts
`+ # .` as part of a token, so `C`, `C++`, `C#`, and `.NET` stay distinct.

**Deduplication costs two queries per poll, no matter the size.** Job IDs live in
SQLite with the ID as the primary key. Each poll reads the known IDs into a set,
filters in memory, then does one batched `INSERT OR IGNORE`. Whether a company
posts 5 roles or 5,000, that is still two round trips to the database.

**One flaky source cannot take down a run.** Sources are fetched concurrently with
a semaphore keeping the request rate polite. Failures are collected rather than
raised, so a company having a bad day gets logged and skipped while everything
else still reports. Notifications fan out the same way.

**Written to be extended by other people.** Sources and notifiers are registered
through Python entry points, so someone can ship a new ATS adapter from their own
package without editing this codebase.

## Project layout

```
src/jobradar/
├── models.py        Job and MatchRule, the two value objects everything shares
├── config.py        The config.yaml schema, plus load and save
├── cli.py           The Typer commands, and the wiring that builds a live run
├── core/            The engine
│   ├── detect.py    Careers URL to ATS to the right adapter
│   ├── matcher.py   Word boundary aware keyword matching
│   ├── dedup.py     SQLite backed set of postings already seen
│   ├── runner.py    One poll: fetch, match, dedup, notify
│   └── scheduler.py Repeats a poll on a fixed interval
├── sources/         Getting postings in
│   ├── base.py      The JobSource contract
│   ├── workday.py   Paginated JSON API, covers every Workday tenant
│   ├── greenhouse.py
│   └── lever.py
└── notifiers/       Sending matches out
    ├── base.py      The Notifier contract
    ├── console.py
    ├── discord.py
    └── telegram.py
```

The two `base.py` files are the whole architecture in miniature. `JobSource.fetch()`
returns normalized `Job` objects, `Notifier.send(jobs)` delivers them, and every
concrete source or notifier is a plugin behind one of those two interfaces. The
matcher and deduplicator never learn which ATS a posting came from.

## Supported today

Sources: Workday, Greenhouse, Lever.
Notifiers: console, Discord, Telegram.

Detection already recognizes iCIMS, Ashby, and SmartRecruiters URLs and will tell
you the platform is known but not yet implemented, so adding those is a new file
plus one line in the registry. Slack, OAuth based notifiers, and an Adzuna
aggregator source are designed for but deliberately left out for now.

## Tech stack

Python 3.11+, managed with [uv](https://docs.astral.sh/uv/). Typer for the CLI,
Pydantic v2 for models and config, httpx for async HTTP, SQLite from the standard
library, structlog for structured logs. Tested with pytest and respx, checked with
ruff and mypy in strict mode.

## Development

```bash
uv sync                 # create the venv and install everything
uv run pytest           # tests
uv run ruff check .     # lint
uv run mypy             # type check
```

Every HTTP call in the test suite is mocked, so nothing hits the network.

## License

[MIT](LICENSE)

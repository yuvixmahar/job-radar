"""Track which jobs we've already seen, so we only notify on genuinely new ones.

SQLite is the source of truth: a single ``seen_jobs(id TEXT PRIMARY KEY)`` table.
Each poll does exactly two queries — one read to load known ids, one batched
``INSERT OR IGNORE`` write — regardless of how many jobs were fetched. The
primary-key B-tree dedups at O(log n); we pre-filter in memory against a set so
the caller learns *which* jobs are new and worth notifying on.

Deliberately synchronous: SQLite is in-process, so making it async would only add
thread hops (see CLAUDE.md, concurrency decision).
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Self

from jobradar.models import Job

_SCHEMA = "CREATE TABLE IF NOT EXISTS seen_jobs (id TEXT PRIMARY KEY)"


class SeenStore:
    """A persistent set of seen job ids, backed by SQLite."""

    def __init__(self, path: Path | str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def known_ids(self) -> set[str]:
        """Return every id recorded so far (one SELECT)."""
        rows = self._conn.execute("SELECT id FROM seen_jobs").fetchall()
        return {str(row[0]) for row in rows}

    def filter_new(self, jobs: Iterable[Job]) -> list[Job]:
        """Record the given jobs and return only the ones never seen before.

        Order-preserving; duplicates *within* this batch collapse to one. Exactly
        two queries: load known ids, then one batched ``INSERT OR IGNORE``.
        """
        known = self.known_ids()
        new: list[Job] = []
        batch_ids: set[str] = set()
        for job in jobs:
            if job.id in known or job.id in batch_ids:
                continue
            batch_ids.add(job.id)
            new.append(job)
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (id) VALUES (?)",
            [(job.id,) for job in new],
        )
        self._conn.commit()
        return new

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

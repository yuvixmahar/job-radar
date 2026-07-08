"""The poll pipeline: fetch → match → dedup → notify, run once per poll.

One :meth:`Runner.run_once` is a single poll. Sources are fetched concurrently
(capped by a semaphore to stay polite), and a source that raises is logged and
skipped rather than sinking the whole run. Matched postings are deduped against
:class:`~jobradar.core.dedup.SeenStore`, and only the genuinely-new matches are
handed to the notifiers (also fanned out concurrently).

Matching happens *before* dedup on purpose: the store then holds "jobs we've
already notified about," so ``run_once`` notifies exactly the matched-and-new
jobs. The runner does not own the HTTP client or build sources — the caller
injects already-constructed sources, notifiers, and store.
"""

import asyncio
from collections.abc import Sequence

import structlog

from jobradar.core.dedup import SeenStore
from jobradar.core.matcher import matches
from jobradar.models import Job, MatchRule
from jobradar.notifiers.base import Notifier
from jobradar.sources.base import JobSource

_log = structlog.get_logger("jobradar.runner")


class Runner:
    """Orchestrates one poll across all sources, notifiers, and the dedup store."""

    def __init__(
        self,
        sources: Sequence[JobSource],
        rule: MatchRule,
        store: SeenStore,
        notifiers: Sequence[Notifier],
        *,
        max_concurrency: int = 8,
    ) -> None:
        self._sources = sources
        self._rule = rule
        self._store = store
        self._notifiers = notifiers
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run_once(self) -> list[Job]:
        """Run one poll; return the matched, never-before-seen jobs notified on."""
        fetched = await self._fetch_all()
        matched = [job for job in fetched if matches(job, self._rule)]
        new_jobs = self._store.filter_new(matched)
        _log.info(
            "run_completed",
            fetched=len(fetched),
            matched=len(matched),
            new=len(new_jobs),
        )
        if new_jobs:
            await self._notify_all(new_jobs)
        return new_jobs

    async def _fetch_all(self) -> list[Job]:
        results = await asyncio.gather(
            *(self._fetch_one(source) for source in self._sources),
            return_exceptions=True,
        )
        fetched: list[Job] = []
        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                _log.warning(
                    "source_failed",
                    source=type(source).__name__,
                    error=str(result),
                )
                continue
            fetched.extend(result)
        return fetched

    async def _fetch_one(self, source: JobSource) -> list[Job]:
        async with self._semaphore:
            return await source.fetch()

    async def _notify_all(self, jobs: list[Job]) -> None:
        results = await asyncio.gather(
            *(notifier.send(jobs) for notifier in self._notifiers),
            return_exceptions=True,
        )
        for notifier, result in zip(self._notifiers, results, strict=True):
            if isinstance(result, BaseException):
                _log.warning(
                    "notifier_failed",
                    notifier=type(notifier).__name__,
                    error=str(result),
                )

"""The ``JobSource`` contract: one adapter per ATS platform.

Every way of getting postings — a Workday tenant, Greenhouse, Lever, later an
aggregator like Adzuna — implements this single async method and returns
normalized :class:`~jobradar.models.Job` objects. The runner fetches all sources
concurrently, so ``fetch`` is a coroutine; how a concrete source gets its HTTP
client (typically injected in ``__init__`` so one pooled client is shared) is an
implementation detail, not part of this contract.
"""

from abc import ABC, abstractmethod

from jobradar.models import Job


class JobSource(ABC):
    """A source of job postings from one ATS platform (never per-company)."""

    @abstractmethod
    async def fetch(self) -> list[Job]:
        """Fetch current postings, normalized to :class:`Job` objects."""
        raise NotImplementedError

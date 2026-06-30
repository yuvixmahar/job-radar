from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Job(BaseModel):
    """A normalized job posting; identity is the `id` alone (the dedup key)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    location: str | None = None
    posted_at: datetime | None = None
    raw: dict[str, Any] | None = Field(default=None, repr=False)

    @classmethod
    def make_id(cls, source: str, *parts: str) -> str:
        """Build a source-namespaced id, e.g. ``workday:ciena:R-12345``."""
        return ":".join([source, *parts])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Job):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

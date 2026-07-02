import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_WHITESPACE = re.compile(r"\s+")


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


class MatchRule(BaseModel):
    """Keywords a posting's title is matched against.

    Keywords are normalized at construction: stripped, internal whitespace
    collapsed, empties dropped, and de-duplicated case-insensitively
    (first occurrence wins). Original casing is preserved for display; the
    matcher compares case-insensitively. An empty list means *match everything*
    (no filter).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    keywords: tuple[str, ...] = ()

    @field_validator("keywords", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            raise ValueError("keywords must be a sequence of strings")
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("keywords must be strings")
            keyword = _WHITESPACE.sub(" ", item).strip()
            key = keyword.lower()
            if keyword and key not in seen:
                seen.add(key)
                normalized.append(keyword)
        return tuple(normalized)

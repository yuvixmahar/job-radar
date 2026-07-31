"""Identify which ATS a careers URL belongs to, and build the right adapter.

The user only ever pastes a careers URL (``jobradar add-company <url>``); this
module decides *which* :class:`~jobradar.sources.base.JobSource` handles it, so
the user never picks an adapter. Detection is pure rules — no AI — by host
fingerprint (``myworkdayjobs.com`` → workday, ``greenhouse.io`` → greenhouse, …).

The registry is built from the ``jobradar.sources`` **entry points**: each source
declares the hosts it handles via :meth:`JobSource.hosts`, so a third party can
ship an adapter from their own package and have it recognized here without editing
core. Recognizing a platform and *having an adapter for it* are still separate — a
small static map names platforms we can fingerprint but haven't implemented yet.
"""

from functools import cache
from importlib.metadata import entry_points
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import structlog

from jobradar.sources.base import JobSource

_log = structlog.get_logger("jobradar.detect")

_SOURCES_GROUP = "jobradar.sources"

# Platforms we can fingerprint but have no adapter for yet: detection names them
# so the CLI can say "known but unimplemented" instead of "unrecognized".
_UNBUILT_MARKERS: dict[str, str] = {"icims.com": "icims"}


class _SourceBuilder(Protocol):
    """An adapter's ``from_url`` classmethod: URL (+ optional company) → source."""

    def __call__(
        self, url: str, client: httpx.AsyncClient, *, company: str | None = None
    ) -> JobSource: ...


@cache
def _registry() -> tuple[dict[str, str], dict[str, _SourceBuilder]]:
    """Load host markers and URL builders from the ``jobradar.sources`` entry points.

    Returns ``(host suffix → key, key → from_url)``. Cached, so entry points are
    read once per process. A plugin that fails to import is logged and skipped
    rather than breaking detection for every other source.
    """
    host_markers: dict[str, str] = dict(_UNBUILT_MARKERS)
    builders: dict[str, _SourceBuilder] = {}
    for entry_point in entry_points(group=_SOURCES_GROUP):
        try:
            source_cls = entry_point.load()
        except Exception as exc:  # a broken third-party plugin shouldn't sink detection
            _log.warning("source_plugin_failed", plugin=entry_point.name, error=str(exc))
            continue
        builders[entry_point.name] = source_cls.from_url
        for host in source_cls.hosts():
            host_markers[host] = entry_point.name
    return host_markers, builders


def detect_ats(url: str) -> str | None:
    """Return the ATS key for a careers URL by host, or ``None`` if unrecognized."""
    host = urlsplit(url).hostname
    if host is None:
        return None
    host = host.lower()
    host_markers, _ = _registry()
    for marker, key in host_markers.items():
        if host == marker or host.endswith("." + marker):
            return key
    return None


def check_supported(url: str) -> str:
    """Return the ATS key if we can build a source for the URL, else raise.

    Client-free validation for ``add-company``. Raises ``ValueError`` if the ATS
    can't be recognized, or ``NotImplementedError`` if it's recognized but has no
    adapter yet.
    """
    key = detect_ats(url)
    if key is None:
        raise ValueError(f"could not detect a known ATS from URL: {url!r}")
    _, builders = _registry()
    if key not in builders:
        raise NotImplementedError(f"detected ATS {key!r}, but no adapter is available yet")
    return key


def build_source(url: str, client: httpx.AsyncClient, *, company: str | None = None) -> JobSource:
    """Build the adapter for a careers URL (see :func:`check_supported` for errors)."""
    key = check_supported(url)
    _, builders = _registry()
    return builders[key](url, client, company=company)

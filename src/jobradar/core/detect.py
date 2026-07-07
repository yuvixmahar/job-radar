"""Identify which ATS a careers URL belongs to, and build the right adapter.

The user only ever pastes a careers URL (``jobradar add-company <url>``); this
module decides *which* :class:`~jobradar.sources.base.JobSource` handles it, so
the user never picks an adapter. Detection is pure rules — no AI:

1. **Host fingerprint** (this unit) — ``myworkdayjobs.com`` → workday,
   ``greenhouse.io`` → greenhouse, … Covers the large majority of URLs with no
   network call.
2. *(later)* follow redirects for custom vanity domains, then
3. *(later)* fetch the page once and scan the HTML for ATS markers.

Recognizing an ATS and *having an adapter for it* are separate: we can fingerprint
all six known platforms, but only build sources for the ones implemented so far.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from jobradar.sources.base import JobSource
from jobradar.sources.workday import WorkdaySource

# Host suffix → ATS key. Matched against the URL's hostname (exact or subdomain).
_HOST_MARKERS: dict[str, str] = {
    "myworkdayjobs.com": "workday",
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
    "icims.com": "icims",
    "smartrecruiters.com": "smartrecruiters",
}

# ATS key → how to build its adapter from a URL. Only implemented adapters
# appear here; keys detectable above but absent here have "no adapter yet".
_BUILDERS: dict[str, Callable[[str, httpx.AsyncClient], JobSource]] = {
    "workday": WorkdaySource.from_url,
}


def detect_ats(url: str) -> str | None:
    """Return the ATS key for a careers URL by host, or ``None`` if unrecognized."""
    host = urlsplit(url).hostname
    if host is None:
        return None
    host = host.lower()
    for marker, key in _HOST_MARKERS.items():
        if host == marker or host.endswith("." + marker):
            return key
    return None


def build_source(url: str, client: httpx.AsyncClient) -> JobSource:
    """Build the adapter for a careers URL.

    Raises ``ValueError`` if the ATS can't be recognized, or ``NotImplementedError``
    if it's recognized but no adapter exists for it yet.
    """
    key = detect_ats(url)
    if key is None:
        raise ValueError(f"could not detect a known ATS from URL: {url!r}")
    builder = _BUILDERS.get(key)
    if builder is None:
        raise NotImplementedError(f"detected ATS {key!r}, but no adapter is available yet")
    return builder(url, client)

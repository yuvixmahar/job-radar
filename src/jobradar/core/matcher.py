"""Match a rule's keywords against a job's text (title, or location).

Matching is *word-boundary aware*, not naive substring: keyword ``C`` matches
"Embedded C Developer" but not "C++" nor "Calculus". ``+ # .`` count as part of
a token, so ``C``, ``C++``, ``C#`` and ``.NET`` are distinct. An empty keyword
list means *match everything* (no filter).

The same boundary-aware engine drives two axes:

- **Title** keywords via :func:`matches` / :func:`matched_keywords`.
- **Location** keywords via :func:`location_matches`, matched against the job's
  free-text ``location``. Because spaces, commas and hyphens are boundaries,
  ``US`` matches "Remote - US" but not "Houston, TX". A non-empty location rule
  also *drops* jobs with no location (we can't confirm the region).
"""

import re
from functools import cache

from jobradar.models import Job, MatchRule

# Characters that count as "inside a word". A keyword only matches when it is
# NOT flanked by one of these, so ``C`` won't fire inside ``C++`` or ``Calculus``.
# Note ``+ # .`` are included, which plain ``\b`` boundaries would not do.
_BOUNDARY = r"A-Za-z0-9+#."


@cache
def _pattern(keyword: str) -> re.Pattern[str]:
    """Compile (once per keyword) the boundary-aware, case-insensitive regex."""
    # Split on whitespace and rejoin with ``\s+`` so intra-keyword spacing is
    # flexible ("machine learning" also matches "machine  learning"); re.escape
    # each part so ``+``/``.``/``#`` are treated literally, not as regex syntax.
    core = r"\s+".join(re.escape(part) for part in keyword.split())
    return re.compile(rf"(?<![{_BOUNDARY}]){core}(?![{_BOUNDARY}])", re.IGNORECASE)


def matched_in(text: str, rule: MatchRule) -> list[str]:
    """Return the rule's keywords found in ``text``, in the rule's order.

    Empty for an empty rule (there are no keywords to report), even though such
    a rule still *matches* everything — see :func:`matches`.
    """
    return [kw for kw in rule.keywords if _pattern(kw).search(text)]


def matched_keywords(job: Job, rule: MatchRule) -> list[str]:
    """The rule's keywords found in the job *title*, in the rule's order."""
    return matched_in(job.title, rule)


def matches(job: Job, rule: MatchRule) -> bool:
    """True if the job title matches the rule. An empty rule matches everything."""
    return not rule.keywords or bool(matched_keywords(job, rule))


def location_matches(job: Job, rule: MatchRule) -> bool:
    """True if the job's location satisfies the location rule.

    An empty rule imposes no filter (every job passes, including those with no
    location). A non-empty rule requires the job to *have* a location that matches
    one of the keywords — jobs with no location are dropped, since we can't confirm
    their region.
    """
    if not rule.keywords:
        return True
    if job.location is None:
        return False
    return bool(matched_in(job.location, rule))

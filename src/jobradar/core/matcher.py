"""Decide whether a job's title matches a rule's keywords.

Matching is *word-boundary aware*, not naive substring: keyword ``C`` matches
"Embedded C Developer" but not "C++" nor "Calculus". ``+ # .`` count as part of
a token, so ``C``, ``C++``, ``C#`` and ``.NET`` are distinct. Scope is the job
*title* only. An empty keyword list means *match everything* (no filter).
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


def matched_keywords(job: Job, rule: MatchRule) -> list[str]:
    """Return the rule's keywords found in the job title, in the rule's order.

    Empty for an empty rule (there are no keywords to report), even though such
    a rule still *matches* every job — see :func:`matches`.
    """
    return [kw for kw in rule.keywords if _pattern(kw).search(job.title)]


def matches(job: Job, rule: MatchRule) -> bool:
    """True if the job title matches the rule. An empty rule matches everything."""
    return not rule.keywords or bool(matched_keywords(job, rule))

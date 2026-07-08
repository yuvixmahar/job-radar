"""Console notifier — print matched jobs to a stream (stdout by default).

The console is the one notifier allowed to ``print``: human-readable output *is*
its delivery channel. The output stream is injectable so it's easy to test and to
redirect. Like every notifier, it assumes the jobs it receives are already matched
and already new — it just formats and prints them.
"""

import sys
from typing import TextIO

from jobradar.models import Job
from jobradar.notifiers.base import Notifier


class ConsoleNotifier(Notifier):
    """Write matched postings to a text stream (defaults to stdout)."""

    def __init__(self, stream: TextIO | None = None) -> None:
        # Resolved at send time (below) so a stream swapped in after construction
        # — e.g. test capture — is still honored.
        self._stream = stream

    async def send(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        stream = self._stream if self._stream is not None else sys.stdout
        # ASCII only: the console's default encoding is not UTF-8 everywhere
        # (e.g. cp1252 on Windows), so fancy bullets/dashes would mojibake.
        lines = [f"{len(jobs)} new job(s):"]
        for job in jobs:
            meta = f"{job.company}, {job.location}" if job.location else job.company
            lines.append(f"  * {job.title}  ({meta})")
            lines.append(f"    {job.url}")
        print("\n".join(lines), file=stream)

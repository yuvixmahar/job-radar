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
        # Our own decoration is ASCII (cp1252 consoles can't do fancy bullets),
        # but job *data* can be any Unicode. Re-encode to the stream's encoding
        # with replacement so a non-ASCII title can't crash the whole run.
        lines = [f"{len(jobs)} new job(s):"]
        for job in jobs:
            meta = f"{job.company}, {job.location}" if job.location else job.company
            lines.append(f"  * {job.title}  ({meta})")
            lines.append(f"    {job.url}")
        text = "\n".join(lines)
        encoding = getattr(stream, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), file=stream)

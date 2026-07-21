"""Build a plain-text summary of new jobs, capped to a channel's length limit.

Shared by the webhook notifiers (Discord ~2000 chars, Telegram ~4096). If the
jobs don't all fit, as many as possible are listed and an "...and N more" line is
appended — a poll that finds hundreds of matches must never exceed the limit and
get rejected by the API.
"""

from jobradar.models import Job

# Room reserved so the trailing "...and N more" line can always be added.
_OVERFLOW_BUDGET = 48


def build_message(jobs: list[Job], *, max_len: int) -> str:
    header = f"{len(jobs)} new job(s):"
    parts = [header]
    total = len(header)
    shown = 0
    for job in jobs:
        block = _job_block(job)
        addition = len(block) + 1  # + the joining newline
        if total + addition > max_len - _OVERFLOW_BUDGET:
            break
        parts.append(block)
        total += addition
        shown += 1
    if shown < len(jobs):
        parts.append(f"...and {len(jobs) - shown} more")
    return "\n".join(parts)


def _job_block(job: Job) -> str:
    location = f" ({job.location})" if job.location else ""
    return f"- {job.title} @ {job.company}{location}\n  {job.url}"

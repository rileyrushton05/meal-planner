"""Security events: one structured log line per thing worth auditing.

Signups, logins (and failures), logouts, guest sessions, throttling and
refused cross-site requests, each as JSON on the `meal_planner.security`
logger, which Vercel keeps as searchable runtime logs. Every line carries
the request id (server/observability.py), so it lines up with the request's
own log line.

What may be recorded is decided here, once: an event takes only the fields
named in `_ALLOWED`, and anything else is a programming error. Never
recorded: passwords, password hashes, session tokens, email addresses or IP
addresses. A log that records what it protects is worse than no log, and
logs are read by more people and systems than the database is. Where an
event needs to say "the same person as before" without saying who, it
carries a short prefix of the throttle's keyed hash (`subject`).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("meal_planner.security")

_ALLOWED = frozenset(
    {
        "user_id",  # an account id: who, without saying who they are
        "outcome",
        "rule",  # which throttle
        "retry_after_seconds",
        "subject",  # a prefix of a keyed hash; correlates attempts only
        "removed",  # counts of rows deleted, by kind
        "changed",  # counts of rows a sync changed, by kind
        "dry_run",
    }
)

#: Enough of a 256-bit keyed hash to tell attempts apart in a log, far too
#: little to be worth attacking.
SUBJECT_PREFIX_LENGTH = 12


def record(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Log one security event, e.g. `record("login_failed", user_id=7)`."""
    unexpected = set(fields) - _ALLOWED
    if unexpected:
        raise ValueError(
            f"Security events may not carry {sorted(unexpected)}; "
            "see app/events.py for what is safe to log."
        )
    if isinstance(fields.get("subject"), str):
        fields["subject"] = str(fields["subject"])[:SUBJECT_PREFIX_LENGTH]
    logger.log(level, event, extra={"event": event, **fields})

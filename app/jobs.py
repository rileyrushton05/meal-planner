"""Scheduled maintenance, run by GitHub Actions (.github/workflows/jobs.yml).

    python -m app.jobs purge-guests [--dry-run]
    python -m app.jobs sync-catalog [--dry-run] [--show-unmatched]

One entry point for every scheduled job, so each is run, logged and
targeted the same way; the price refresh (Phase 4) joins it here. Jobs
connect as the database owner, not the web app's role: their work spans
users, which row-level security exists to prevent the app from doing. The
URL must be named in the shell (or by CI) for a database that is not on
this machine; `.env` is never enough (`resolve_migration_url`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy.engine import make_url
from sqlmodel import Session

from app import events
from app.auth import SESSION_LIFETIME
from app.catalog import load_catalog, plan_sync
from app.db import Database
from app.migrations import resolve_migration_url
from app.ratelimit import STALE_AFTER
from app.repositories import (
    CatalogRepository,
    RateLimitRepository,
    SessionRepository,
    UserRepository,
)

#: A guest not seen for this long is deleted with everything they made.
#: Matches the session lifetime: by then their cookie no longer works, so
#: nobody can reach the data anyway.
GUEST_IDLE_LIMIT = SESSION_LIFETIME


@dataclass(frozen=True, slots=True)
class Purged:
    guests: int
    sessions: int
    rate_limits: int


def purge_guests(session: Session, *, now: datetime, dry_run: bool) -> Purged:
    """Remove what can no longer be used: guests idle past the limit (and,
    through ON DELETE CASCADE, their meals, plans and sessions), expired
    sessions of any account, and throttle buckets past every rule's window.
    """
    return Purged(
        guests=UserRepository(session).purge_idle_guests(
            now - GUEST_IDLE_LIMIT, dry_run=dry_run
        ),
        sessions=SessionRepository(session).purge_expired(now, dry_run=dry_run),
        rate_limits=RateLimitRepository(session).purge_stale(
            now - STALE_AFTER, now, dry_run=dry_run
        ),
    )


@dataclass(frozen=True, slots=True)
class CatalogSynced:
    added: int
    updated: int
    removed: int
    linked: int
    unlinked: int
    unmatched: int
    #: The names behind `unmatched`. Users' own words, so never logged or
    #: printed by default: Actions logs of a public repository are public.
    unmatched_names: tuple[str, ...] = ()


def sync_catalog(session: Session, *, now: datetime, dry_run: bool) -> CatalogSynced:
    """Load app/catalog.csv: add, update and remove items to match it,
    rebuild the aliases, and relink every ingredient. Running it twice
    changes nothing the second time."""
    catalog = CatalogRepository(session)
    plan = plan_sync(load_catalog(), catalog.items(), catalog.every_ingredient())
    if not dry_run:
        catalog.apply(plan)
    return CatalogSynced(
        added=len(plan.add),
        updated=len(plan.update),
        removed=len(plan.remove),
        linked=sum(1 for key in plan.relink.values() if key is not None),
        unlinked=sum(1 for key in plan.relink.values() if key is None),
        unmatched=len(plan.unmatched),
        unmatched_names=tuple(sorted(set(plan.unmatched), key=str.casefold)),
    )


Job = Callable[..., Purged | CatalogSynced]
JOBS: dict[str, Job] = {"purge-guests": purge_guests, "sync-catalog": sync_catalog}
#: How each job reports: (done, dry run, the event field for its counts).
_REPORTS = {
    "purge-guests": ("Removed", "Would remove", "removed"),
    "sync-catalog": ("Synced", "Would sync", "changed"),
}


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument("job", choices=sorted(JOBS))
    parser.add_argument(
        "--dry-run", action="store_true", help="count what would change; change nothing"
    )
    parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="sync-catalog: list ingredient names no item matched (local use only)",
    )
    args = parser.parse_args(argv)

    # Its own process, so its own log output: the security events it records
    # (app/events.py) go to stderr, which the Actions log keeps.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    url = resolve_migration_url(None)
    print(f"Target database: {make_url(url).render_as_string(hide_password=True)}")
    moment = now or datetime.now(UTC)
    with Database(url).transaction() as session:
        result = JOBS[args.job](session, now=moment, dry_run=args.dry_run)

    done, would, field = _REPORTS[args.job]
    counts = {kind: n for kind, n in asdict(result).items() if isinstance(n, int)}
    summary = ", ".join(f"{n} {kind.replace('_', ' ')}" for kind, n in counts.items())
    print(f"{would if args.dry_run else done}: {summary}")
    if args.show_unmatched and isinstance(result, CatalogSynced):
        for name in result.unmatched_names:
            print(f"  not in the catalogue: {name}")
    event = args.job.replace("-", "_")
    if field == "removed":
        events.record(event, removed=counts, dry_run=args.dry_run)
    else:
        events.record(event, changed=counts, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

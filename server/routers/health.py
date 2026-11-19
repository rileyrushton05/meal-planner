"""Health checks for the platform and the keep-warm schedule.

``/health/live`` answers whether the process can serve at all, and touches
nothing else. ``/health/ready`` also checks the database, with a bounded
wait, so a probe can tell "up" from "up but unable to do anything useful".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import ratelimit
from app.readiness import check_database_ready
from server.deps import get_database
from server.problems import problem_response

router = APIRouter(tags=["ops"])
logger = logging.getLogger("meal_planner.api")


@router.get("/health/live")
@router.get("/health", include_in_schema=False)
def live() -> dict[str, str]:
    """The process is running. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
def ready(request: Request) -> dict[str, str] | JSONResponse:
    """The configuration is complete and the database has the tables,
    columns and permissions this application needs.

    Configuration first: a deployment missing a required secret can reach
    its database and serve reads, then fail on the first sign-in. That
    happened to preview deployments, which had the database URL but not the
    rate-limit key; this makes it visible to anyone who checks.

    The probes are read-only, need no session or access to migration
    history, and accept compatible additive schema changes. PostgreSQL
    queries and lock waits have transaction-local timeouts.
    """
    try:
        ratelimit.check_configured()
    except RuntimeError as exc:
        # The log names what is missing (a setting's name, not a secret);
        # the response, which anyone can read, does not.
        logger.error("readiness check failed: %s", exc)
        return problem_response(
            request,
            status=503,
            slug="not-ready",
            detail="The service is missing required configuration.",
        )
    try:
        check_database_ready(get_database().engine)
    except Exception as exc:
        logger.warning("readiness check failed: %s", type(exc).__name__)
        return problem_response(
            request,
            status=503,
            slug="not-ready",
            detail="The service's database is unavailable or not ready.",
        )
    return {"status": "ok"}

"""FastAPI application.

Run locally with:
    uvicorn server.main:app --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import is_local_database
from app.migrations import upgrade_to_head
from server.deps import get_database
from server.headers import SecurityHeadersMiddleware
from server.monitoring import init_error_tracking
from server.observability import RequestContextMiddleware, configure_logging
from server.origin import reject_cross_site_writes, trusted_origins
from server.problems import (
    UnexpectedErrorMiddleware,
    document_problem_responses,
    install_problem_handlers,
)
from server.routers import account, auth, health, meals, monitoring, plans, state

configure_logging()
init_error_tracking()

#: Whether to apply migrations at startup. Sensible for a long-lived server,
#: wrong for serverless: every cold start would re-check the schema, and two
#: functions starting at once could try to migrate concurrently. On Vercel
#: this is set to "false" and migrations are applied from CI instead.
AUTO_MIGRATE_ENV_VAR = "MEAL_PLANNER_AUTO_MIGRATE"


def _auto_migrate_enabled(url: str) -> bool:
    configured = os.getenv(AUTO_MIGRATE_ENV_VAR)
    if configured is not None:
        return configured.lower() == "true"
    # Off on Vercel (VERCEL is set for every deployment), and off for any
    # database not on this machine: a dev server started on a feature branch
    # with .env pointing at production would otherwise migrate production.
    return os.getenv("VERCEL") is None and is_local_database(url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the schema up to date once, before serving any request."""
    url = get_database().url
    if _auto_migrate_enabled(url):
        upgrade_to_head(url)
    yield


app = FastAPI(
    title="The Fridge Door API",
    version="1.0.0",
    summary="Plan a week of meals and get a consolidated grocery list.",
    lifespan=lifespan,
    # Every route: refuse writes another website sends (server/origin.py).
    dependencies=[Depends(reject_cross_site_writes)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=trusted_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette runs the middleware added last first, so the order on the way in
# is: request context, security headers, unexpected-error handling, then
# CORS. Every response, including those CORS or the error handling writes,
# gets a request id, the security headers and a completion log line.
app.add_middleware(UnexpectedErrorMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

install_problem_handlers(app)
document_problem_responses(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(state.router)
app.include_router(meals.router)
app.include_router(plans.router)
app.include_router(monitoring.router)

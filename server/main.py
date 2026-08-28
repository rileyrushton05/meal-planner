"""FastAPI application.

Run locally with:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.deps import _database
from server.routers import meals, plans, state
from app.exceptions import (
    DuplicateNameError,
    MealNotFoundError,
    MealPlannerError,
    UnitMismatchError,
)
from app.migrations import upgrade_to_head

#: Comma-separated origins allowed to call the API. The deployed frontend's
#: URL goes here; localhost defaults cover development.
CORS_ORIGINS_ENV_VAR = "MEAL_PLANNER_CORS_ORIGINS"
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


#: Whether to apply migrations at startup. Sensible for a long-lived server,
#: wrong for serverless: every cold start would re-check the schema, and two
#: functions starting at once could try to migrate concurrently. On Vercel
#: this is set to "false" and migrations are applied from CI instead.
AUTO_MIGRATE_ENV_VAR = "MEAL_PLANNER_AUTO_MIGRATE"


def _auto_migrate_enabled() -> bool:
    configured = os.getenv(AUTO_MIGRATE_ENV_VAR)
    if configured is not None:
        return configured.lower() == "true"
    # Vercel sets this for every deployment; default off there.
    return os.getenv("VERCEL") is None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the schema up to date once, before serving any request."""
    if _auto_migrate_enabled():
        upgrade_to_head(_database().url)
    yield


app = FastAPI(
    title="Meal Planner API",
    version="1.0.0",
    summary="Plan a week of meals and get a consolidated grocery list.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(CORS_ORIGINS_ENV_VAR, _DEFAULT_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(state.router)
app.include_router(meals.router)
app.include_router(plans.router)


#: Domain errors carry messages written for the person using the app, so they
#: are surfaced verbatim rather than replaced with a generic string.
_STATUS_BY_ERROR = {
    MealNotFoundError: 404,
    DuplicateNameError: 409,
    UnitMismatchError: 409,
}


@app.exception_handler(MealPlannerError)
async def handle_domain_error(request: Request, exc: MealPlannerError) -> JSONResponse:
    status_code = next(
        (code for kind, code in _STATUS_BY_ERROR.items() if isinstance(exc, kind)),
        400,
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe for the host platform. Does not touch the database."""
    return {"status": "ok"}

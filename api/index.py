"""Vercel serverless entry point.

Vercel turns each .py file under /api into its own serverless function, so
this directory holds exactly one file. The application lives in `server`;
this module only exposes it as the ASGI handler Vercel looks for.

It also times its own import, which happens once per cold start: one log
line (`"event": "cold_start"`) says how long loading the app took, so a
slow first request can be told apart from a slow database.
"""

import logging
import time

_started = time.perf_counter()

from server.main import app  # noqa: E402  (timed, so imported after the clock starts)

logging.getLogger("meal_planner.startup").info(
    "cold start",
    extra={
        "event": "cold_start",
        "import_ms": round((time.perf_counter() - _started) * 1000, 1),
    },
)

__all__ = ["app"]

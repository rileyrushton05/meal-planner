"""Relay for the browser's error reports, on their way to Sentry.

The page sends its reports here rather than to Sentry directly, for two
reasons: the page's Content-Security-Policy stays ``connect-src 'self'``,
and ad blockers, which drop requests to Sentry's domains, let a request to
the app's own API through. Sentry calls this a tunnel.

It is not an open relay. A report is forwarded only if it is addressed to
this deployment's own Sentry project, and only up to a size limit. It needs
no session, because the errors most worth hearing about can happen before
one exists; the app-wide check still refuses reports another website sends.

It deliberately touches no database, so it has no rate limit of its own:
errors are often *caused* by the database being unavailable, and reporting
them must not depend on it. Sentry's own quotas and spike protection limit
what a flood could cost.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool

from server.monitoring import configured_dsn
from server.problems import problem_response

router = APIRouter(tags=["ops"])
logger = logging.getLogger("meal_planner.api")

ENVELOPE_PATH = "/api/monitoring/envelope"
#: Comfortably above a real error report (a few kilobytes), far below
#: anything worth abusing.
MAX_ENVELOPE_BYTES = 200_000
FORWARD_TIMEOUT_SECONDS = 3


@dataclass(frozen=True, slots=True)
class SentryProject:
    host: str
    project_id: str
    public_key: str

    @property
    def envelope_url(self) -> str:
        return f"https://{self.host}/api/{self.project_id}/envelope/"


def parse_dsn(dsn: str) -> SentryProject | None:
    """`https://<public key>@<host>/<project id>`, or None if it is not one."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return None
    project_id = parts.path.strip("/")
    if parts.scheme != "https" or not parts.hostname or not parts.username:
        return None
    if not project_id.isdigit():
        return None
    return SentryProject(parts.hostname, project_id, parts.username)


@router.post(
    ENVELOPE_PATH,
    status_code=204,
    response_class=Response,
    summary="Relay a browser error report to Sentry",
)
async def relay_error_report(request: Request) -> Response:
    body = await _read_at_most(request, MAX_ENVELOPE_BYTES)
    if body is None:
        return problem_response(
            request,
            status=413,
            slug="report-too-large",
            detail="That error report is too large to send.",
        )

    ours = parse_dsn(configured_dsn() or "")
    if ours is None:
        # Error tracking is off here: accept the report and drop it, so the
        # page has nothing to retry.
        return Response(status_code=204)

    addressed_to = _envelope_dsn(body)
    if addressed_to != ours:
        return problem_response(
            request,
            status=400,
            slug="not-our-project",
            detail="That error report is not for this app.",
        )

    await run_in_threadpool(_forward, ours.envelope_url, body)
    return Response(status_code=204)


async def _read_at_most(request: Request, limit: int) -> bytes | None:
    """The body, or None if it is longer than `limit` bytes. Stops reading
    as soon as it is, rather than buffering whatever was sent."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            return None
    return bytes(body)


def _envelope_dsn(body: bytes) -> SentryProject | None:
    """The project an envelope is addressed to: its first line is a JSON
    header naming the DSN."""
    header_line = body.split(b"\n", 1)[0]
    try:
        header = json.loads(header_line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    dsn = header.get("dsn") if isinstance(header, dict) else None
    return parse_dsn(dsn) if isinstance(dsn, str) else None


def _forward(url: str, body: bytes) -> None:
    """Send the envelope on. A failure is logged, not raised: the report is
    lost either way, and the page has nothing useful to do about it."""
    outgoing = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-sentry-envelope"},
    )
    try:
        with urllib.request.urlopen(outgoing, timeout=FORWARD_TIMEOUT_SECONDS):
            pass
    except (URLError, OSError) as error:
        logger.warning("error report not forwarded to Sentry: %s", type(error).__name__)

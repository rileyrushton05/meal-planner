"""Error tracking: unexpected failures, reported to Sentry.

Off unless ``SENTRY_DSN`` is set, so local runs and tests send nothing.
What a report may contain is decided here, not left to the SDK's defaults:

- No personal data. ``send_default_pii`` is off, so no cookies, IP address
  or user; request bodies are never attached; and local variables are not
  captured, because a frame in the login code holds the password.
- No email addresses anywhere. A database error can quote the row it
  rejected; every string in a report is scrubbed before it leaves.
- Exactly one report per unexpected failure. The SDK's automatic web
  framework integrations are off: `UnexpectedErrorMiddleware` already
  catches every unhandled exception, and reports it itself with the
  request id, so a Sentry issue leads straight to the matching log lines.

Log records become breadcrumbs (the trail leading up to an error), never
reports of their own. The application's logs are written to carry no
personal data (app/events.py), and they are scrubbed like everything else.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, cast

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

if TYPE_CHECKING:
    from sentry_sdk._types import Breadcrumb, BreadcrumbHint, Event, Hint

SENTRY_DSN_ENV_VAR = "SENTRY_DSN"

#: Anything shaped like an email address, wherever it appears in a report.
_EMAIL = re.compile(r"[^\s@<>()\[\]{}\"',;:]+@[^\s@<>()\[\]{}\"',;:]+\.[A-Za-z]{2,}")
EMAIL_PLACEHOLDER = "[email]"

#: The parts of a request a report may keep. Headers, cookies, the body,
#: the query string and the environment are dropped.
_REQUEST_KEEPS = ("method", "url")


def configured_dsn() -> str | None:
    return os.getenv(SENTRY_DSN_ENV_VAR) or None


def init_error_tracking(
    dsn: str | None = None, *, transport: type[Transport] | None = None
) -> bool:
    """Start reporting to Sentry if a DSN is configured. Returns whether it
    did. `transport` lets tests capture reports instead of sending them."""
    dsn = dsn or configured_dsn()
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("VERCEL_ENV", "development"),
        release=os.getenv("VERCEL_GIT_COMMIT_SHA") or None,
        # Every kind of personal data the SDK could attach, turned off by
        # name rather than trusting a default.
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "off"}},
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "database_query_data": False,
            "stack_frame_variables": False,
        },
        include_local_variables=False,
        max_request_body_size="never",
        auto_enabling_integrations=False,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=None)],
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        transport=transport,
    )
    sentry_sdk.set_tag("side", "api")
    return True


def report_unexpected_error(
    error: BaseException, *, request_id: str | None, method: str, path: str
) -> None:
    """Report an unhandled exception, tagged so it can be found in the logs.
    Does nothing when error tracking is off."""
    if not sentry_sdk.get_client().is_active():
        return
    with sentry_sdk.new_scope() as scope:
        if request_id:
            scope.set_tag("request_id", request_id)
        scope.add_event_processor(
            lambda event, _hint: {**event, "request": {"method": method, "url": path}}
        )
        scope.capture_exception(error)


def scrub_event(event: Event, _hint: Hint) -> Event:
    """Remove personal data from a report before it is sent."""
    event.pop("user", None)
    if isinstance(request := event.get("request"), dict):
        event["request"] = {k: request[k] for k in _REQUEST_KEEPS if k in request}
    return cast("Event", _without_emails(event))


def scrub_breadcrumb(crumb: Breadcrumb, _hint: BreadcrumbHint) -> Breadcrumb:
    return cast("Breadcrumb", _without_emails(crumb))


def _without_emails(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL.sub(EMAIL_PLACEHOLDER, value)
    if isinstance(value, dict):
        return {key: _without_emails(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_without_emails(item) for item in value]
    return value

"""Error tracking: what reaches Sentry, and what never does.

Reports are captured in memory by a test transport; nothing is sent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

import pytest
import sentry_sdk
from api_client import api_client
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.repositories import MealRepository
from server.deps import SESSION_COOKIE
from server.monitoring import EMAIL_PLACEHOLDER, init_error_tracking, scrub_event
from server.routers import monitoring as relay
from server.routers.monitoring import ENVELOPE_PATH, MAX_ENVELOPE_BYTES

if TYPE_CHECKING:
    from sentry_sdk._types import Event

DSN = "https://publickey@o1.ingest.de.sentry.io/42"
PROBLEM = "urn:meal-planner:problem:"


class CapturingTransport(Transport):
    """Keeps every report in memory instead of sending it."""

    sent: ClassVar[list[Event]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            CapturingTransport.sent.append(event)


@pytest.fixture
def reports(db):
    CapturingTransport.sent = []
    assert init_error_tracking(DSN, transport=CapturingTransport)
    yield CapturingTransport.sent
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)  # off again for every other test


@pytest.fixture
def client(db):
    with api_client() as client:
        yield client


def _explode_with(monkeypatch, message: str) -> None:
    def explode(self):
        # A local that must never be sent. Built at run time, so the value
        # is not also in the source lines a report quotes around each frame.
        password = " ".join(["lettuce", "harbour", "spoon"])
        raise RuntimeError(message + password[:0])

    monkeypatch.setattr(MealRepository, "list_all_with_ingredients", explode)


# --- Reports from the API ------------------------------------------------------


def test_an_unexpected_failure_is_reported_once_with_its_request_id(
    reports, client, monkeypatch
):
    _explode_with(monkeypatch, "boom")

    response = client.get("/api/meals")

    assert response.status_code == 500
    assert len(reports) == 1
    event = reports[0]
    assert event["tags"]["request_id"] == response.headers["x-request-id"]
    assert event["tags"]["side"] == "api"
    assert event["exception"]["values"][-1]["type"] == "RuntimeError"
    assert event["request"] == {"method": "GET", "url": "/api/meals"}


def test_a_report_carries_no_personal_data(reports, client, monkeypatch):
    _explode_with(monkeypatch, "duplicate key: cook@example.com already exists")

    client.get("/api/meals")

    sent = json.dumps(reports[0])
    assert "cook@example.com" not in sent
    assert EMAIL_PLACEHOLDER in sent
    assert client.cookies.get(SESSION_COOKIE) not in sent
    assert "lettuce harbour spoon" not in sent
    assert "user" not in reports[0]
    frames = reports[0]["exception"]["values"][-1]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)


def test_expected_errors_are_not_reported(reports, client):
    """A missing meal or a wrong password is the app working, not a bug."""
    assert client.get("/api/meals/999999").status_code == 404
    assert (
        client.post(
            "/api/auth/login", json={"email": "a@b.co", "password": "x"}
        ).status_code
        == 401
    )

    assert reports == []


def test_without_a_dsn_nothing_is_set_up(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    assert init_error_tracking() is False
    assert not sentry_sdk.get_client().is_active()


def test_scrubbing_reaches_every_string_and_drops_request_details():
    event: Event = {
        "user": {"email": "cook@example.com", "ip_address": "203.0.113.9"},
        "request": {
            "method": "POST",
            "url": "/api/auth/login",
            "headers": {"Cookie": "__Host-session=abc"},
            "data": {"password": "hunter2"},
            "query_string": "email=cook@example.com",
        },
        "breadcrumbs": {
            "values": [{"message": "signed up as Cook.Two+x@mail.example.org"}]
        },
    }

    scrubbed = scrub_event(event, {})

    assert "user" not in scrubbed
    assert scrubbed["request"] == {"method": "POST", "url": "/api/auth/login"}
    assert scrubbed["breadcrumbs"]["values"][0]["message"] == "signed up as [email]"


# --- The relay for the browser's reports ---------------------------------------


def _envelope(dsn: str = DSN, size: int = 0) -> bytes:
    header = json.dumps({"dsn": dsn, "sent_at": "2026-11-19T00:00:00Z"})
    item = json.dumps({"type": "event"})
    payload = json.dumps({"message": "x" * size})
    return f"{header}\n{item}\n{payload}\n".encode()


@pytest.fixture
def forwarded(monkeypatch):
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(relay, "_forward", lambda url, body: sent.append((url, body)))
    return sent


@pytest.fixture
def stranger(db):
    """No session: reports can come from a page that has not started one."""
    with api_client(as_guest=False) as client:
        yield client


def test_a_report_for_our_project_is_forwarded(stranger, forwarded, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", DSN)
    body = _envelope()

    response = stranger.post(ENVELOPE_PATH, content=body)

    assert response.status_code == 204
    assert forwarded == [("https://o1.ingest.de.sentry.io/api/42/envelope/", body)]


@pytest.mark.parametrize(
    "body",
    [
        _envelope("https://publickey@o1.ingest.de.sentry.io/43"),  # another project
        _envelope("https://otherkey@o1.ingest.de.sentry.io/42"),  # another key
        _envelope("https://publickey@evil.example/42"),  # another host
        b"not an envelope",
        b"",
    ],
    ids=["other project", "other key", "other host", "garbage", "empty"],
)
def test_a_report_for_anyone_else_is_refused(stranger, forwarded, monkeypatch, body):
    monkeypatch.setenv("SENTRY_DSN", DSN)

    response = stranger.post(ENVELOPE_PATH, content=body)

    assert response.status_code == 400
    assert response.json()["type"] == f"{PROBLEM}not-our-project"
    assert forwarded == []


def test_an_oversized_report_is_refused_without_forwarding(
    stranger, forwarded, monkeypatch
):
    monkeypatch.setenv("SENTRY_DSN", DSN)

    response = stranger.post(ENVELOPE_PATH, content=_envelope(size=MAX_ENVELOPE_BYTES))

    assert response.status_code == 413
    assert response.json()["type"] == f"{PROBLEM}report-too-large"
    assert forwarded == []


def test_with_error_tracking_off_reports_are_accepted_and_dropped(
    stranger, forwarded, monkeypatch
):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    assert stranger.post(ENVELOPE_PATH, content=_envelope()).status_code == 204
    assert forwarded == []


def test_another_website_cannot_send_reports(stranger, forwarded, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", DSN)

    response = stranger.post(
        ENVELOPE_PATH, content=_envelope(), headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert forwarded == []

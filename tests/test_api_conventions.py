"""The API's cross-cutting contract: error shape, request strictness, HTTP
semantics, request correlation, logging and health checks.

These are the conventions in docs/conventions.md. Each test names the rule it
holds the API to, so a failure reads as "which promise broke".
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from api_client import api_client

from app.db import Database
from app.repositories import MealRepository
from server.observability import configure_logging
from server.routers import health

PROBLEM_JSON = "application/problem+json"


@pytest.fixture
def client(db):
    with api_client(raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def log_lines():
    """Route the app's logs, as JSON, into a buffer the test can read."""
    buffer = io.StringIO()
    configure_logging(stream=buffer, fmt="json")

    def read() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line]

    yield read
    configure_logging()


def _meal(client, name="Spaghetti") -> dict:
    response = client.post("/api/meals", json={"name": name, "servings": 4})
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------- RFC 9457 problem details


def _assert_problem(response, status: int) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == status
    assert body["type"].startswith("urn:meal-planner:problem:") or body["type"] == (
        "about:blank"
    )
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]
    return body


def test_a_domain_error_is_a_problem_with_its_message_as_detail(client):
    _meal(client)

    response = client.post("/api/meals", json={"name": "spaghetti"})

    body = _assert_problem(response, 409)
    assert body["type"] == "urn:meal-planner:problem:duplicate-name"
    assert "already exists" in body["detail"]
    assert body["instance"] == "/api/meals"


def test_a_missing_meal_is_a_not_found_problem(client):
    body = _assert_problem(client.get("/api/meals/999"), 404)

    assert body["type"] == "urn:meal-planner:problem:meal-not-found"


def test_an_unknown_route_is_a_problem_too(client):
    _assert_problem(client.get("/api/no-such-thing"), 404)


def test_a_wrong_method_is_a_problem(client):
    _assert_problem(client.delete("/api/state"), 405)


def test_validation_errors_list_each_invalid_parameter(client):
    response = client.post("/api/meals", json={"name": "Tacos", "servings": 0})

    body = _assert_problem(response, 422)
    assert body["type"] == "urn:meal-planner:problem:request-validation"
    names = [param["name"] for param in body["invalid_params"]]
    assert names == ["body.servings"]
    # The detail is a sentence the UI can show, not a field path.
    assert "servings" not in body["detail"]


def test_an_unexpected_failure_is_a_sanitised_problem(client, monkeypatch):
    def explode(self):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(MealRepository, "list_all_with_ingredients", explode)

    response = client.get("/api/meals")

    body = _assert_problem(response, 500)
    assert "secret internal detail" not in response.text
    assert body["type"] == "urn:meal-planner:problem:internal"


# ------------------------------------------------------ strict requests


def test_an_unknown_field_is_rejected_rather_than_ignored(client):
    """A misspelt field used to vanish silently: "serving": 6 created a meal
    for one, and nothing said why."""
    response = client.post("/api/meals", json={"name": "Tacos", "serving": 6})

    body = _assert_problem(response, 422)
    assert [p["name"] for p in body["invalid_params"]] == ["body.serving"]


def test_an_unknown_field_inside_a_plan_day_is_rejected(client):
    meal = _meal(client)

    response = client.put(
        "/api/plan/2026-08-03",
        json={"days": [{"day": "Monday", "meal_id": meal["id"], "serves": 2}]},
    )

    _assert_problem(response, 422)


# --------------------------------------------------------- HTTP semantics


def test_creating_a_meal_returns_its_location(client):
    response = client.post("/api/meals", json={"name": "Tacos", "servings": 2})

    assert response.status_code == 201
    location = response.headers["location"]
    assert location == f"/api/meals/{response.json()['id']}"
    assert client.get(location).json() == response.json()


def test_creating_from_a_template_returns_its_location(client):
    response = client.post("/api/meals/from-template/Spaghetti Bolognese")

    assert response.status_code == 201
    assert client.get(response.headers["location"]).json()["name"] == (
        "Spaghetti Bolognese"
    )


# ---------------------------------------------------- request correlation


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/meals"),
        ("get", "/api/meals/999"),
        ("get", "/api/no-such-thing"),
        ("get", "/health/live"),
    ],
)
def test_every_response_carries_a_request_id(client, method, path):
    response = getattr(client, method)(path)

    uuid.UUID(response.headers["x-request-id"])


def test_cors_preflight_responses_carry_a_request_id_too(client):
    """The correlation middleware wraps CORS, so even responses CORS writes
    itself can be traced."""
    response = client.options(
        "/api/meals",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "x-request-id" in response.headers


def test_each_request_gets_its_own_id(client):
    first = client.get("/health/live").headers["x-request-id"]
    second = client.get("/health/live").headers["x-request-id"]

    assert first != second


def test_a_client_supplied_request_id_is_not_trusted(client):
    """A caller could otherwise forge ids to muddle the logs."""
    response = client.get("/health/live", headers={"X-Request-ID": "forged"})

    assert response.headers["x-request-id"] != "forged"


# ---------------------------------------------------------------- logging


def test_each_request_logs_one_structured_completion_event(client, log_lines):
    meal = _meal(client)

    response = client.get(f"/api/meals/{meal['id']}?unused=secret")

    completed = [
        line
        for line in log_lines()
        if line.get("event") == "http_request_completed"
        and line["request_id"] == response.headers["x-request-id"]
    ]
    assert len(completed) == 1
    event = completed[0]
    # The route template, so events aggregate per endpoint and no id or
    # query string is logged.
    assert event["route"] == "/api/meals/{meal_id}"
    assert event["method"] == "GET"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], int | float)
    assert "secret" not in json.dumps(event)


def test_an_unexpected_failure_is_logged_with_its_request_id(
    client, log_lines, monkeypatch
):
    def explode(self):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(MealRepository, "list_all_with_ingredients", explode)

    response = client.get("/api/meals")

    errors = [line for line in log_lines() if line["level"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["request_id"] == response.headers["x-request-id"]
    assert "GET /api/meals" in errors[0]["message"]
    # The traceback reaches the logs, which is where it belongs.
    assert "RuntimeError" in errors[0]["exception"]


def test_an_integrity_error_is_logged_as_a_warning(client, log_lines, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    def collide(self, name, servings=1):
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    monkeypatch.setattr(MealRepository, "add", collide)

    response = client.post("/api/meals", json={"name": "Tacos"})

    _assert_problem(response, 409)
    assert "duplicate key" not in response.text
    assert any(line["level"] == "WARNING" for line in log_lines())


# ------------------------------------------------------------------ health


def test_liveness_needs_no_database(client, monkeypatch):
    def unreachable():
        raise AssertionError("liveness must not touch the database")

    monkeypatch.setattr(health, "get_database", unreachable)

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_checks_the_database(client):
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_readiness_fails_as_a_problem_when_the_database_is_down(
    client, monkeypatch, tmp_path
):
    unreachable = Database(f"sqlite:///{tmp_path / 'missing-dir' / 'x.db'}")
    monkeypatch.setattr(health, "get_database", lambda: unreachable)

    body = _assert_problem(client.get("/health/ready"), 503)
    assert body["type"] == "urn:meal-planner:problem:not-ready"


def test_readiness_fails_when_required_configuration_is_missing(client, monkeypatch):
    """As preview deployments did: the database reachable, but no key to
    hash emails and addresses with, so every sign-in would fail."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("MEAL_PLANNER_RATE_LIMIT_KEY", raising=False)

    response = client.get("/health/ready")

    body = _assert_problem(response, 503)
    assert body["detail"] == "The service is missing required configuration."
    assert "MEAL_PLANNER_RATE_LIMIT_KEY" not in response.text


def test_readiness_passes_with_the_configuration_on_vercel(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("MEAL_PLANNER_RATE_LIMIT_KEY", "test-only-key")

    assert client.get("/health/ready").json() == {"status": "ok"}

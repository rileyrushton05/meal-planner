"""Security headers: the API's, set by the app (server/headers.py), and the
web page's, declared in vercel.json because Vercel's CDN serves the page.

The browser-side proof, that the page works under its policy and the policy
is enforced, is in web/e2e/security.spec.ts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from api_client import api_client

from app.repositories import MealRepository
from server.headers import API_SECURITY_HEADERS

VERCEL_JSON = Path(__file__).resolve().parents[1] / "vercel.json"


@pytest.fixture
def client(db):
    with api_client(raise_server_exceptions=False) as test_client:
        yield test_client


def _assert_api_headers(response) -> None:
    for name, value in API_SECURITY_HEADERS.items():
        assert response.headers.get(name) == value, name


# --- The API -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/state", 200),
        ("GET", "/health", 200),
        ("GET", "/api/no-such-thing", 404),
        ("POST", "/api/meals", 422),
    ],
)
def test_every_api_response_carries_the_headers(client, method, path, status) -> None:
    response = client.request(method, path, json={} if method == "POST" else None)

    assert response.status_code == status
    _assert_api_headers(response)


def test_an_unexpected_failure_carries_them_too(client, monkeypatch) -> None:
    """The error handling writes the 500 itself; the headers must not depend
    on a route having run."""

    def explode(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(MealRepository, "list_all_with_ingredients", explode)

    response = client.get("/api/meals")

    assert response.status_code == 500
    _assert_api_headers(response)


def test_a_signed_out_request_carries_them(db) -> None:
    with api_client(as_guest=False) as anonymous:
        response = anonymous.get("/api/state")

    assert response.status_code == 401
    _assert_api_headers(response)


# --- The web page (vercel.json) ----------------------------------------------


def _page_rule() -> dict:
    config = json.loads(VERCEL_JSON.read_text())
    rules = [r for r in config.get("headers", []) if not r["source"].startswith("/api")]
    assert len(rules) == 1, "expected one header rule for the web page"
    return rules[0]


def _page_headers() -> dict[str, str]:
    return {h["key"]: h["value"] for h in _page_rule()["headers"]}


def _directives(policy: str) -> dict[str, list[str]]:
    parts = (d.split() for d in policy.split(";") if d.strip())
    return {name: values for name, *values in parts}


@pytest.mark.parametrize(
    "path", ["/", "/meals", "/plan", "/groceries", "/assets/index.js"]
)
def test_the_page_rule_covers_every_page_and_asset(path) -> None:
    assert re.fullmatch(_page_rule()["source"], path)


@pytest.mark.parametrize(
    "path", ["/api/state", "/api/auth/login", "/health", "/health/ready"]
)
def test_the_page_rule_leaves_the_api_to_the_app(path) -> None:
    """Two policies on one response would combine, and vercel.json's would
    loosen nothing but could confuse; the API sets its own, stricter set."""
    assert not re.fullmatch(_page_rule()["source"], path)


def test_the_page_policy_allows_nothing_from_elsewhere_and_nothing_inline() -> None:
    policy = _directives(_page_headers()["Content-Security-Policy"])

    for name, sources in policy.items():
        assert "'unsafe-inline'" not in sources, name
        assert "'unsafe-eval'" not in sources, name
        assert "*" not in sources and "data:" not in sources, name
        assert all(s.startswith("'") for s in sources), (
            f"{name} allows a host: {sources}"
        )
    assert policy["default-src"] == ["'self'"]
    assert policy["script-src"] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["base-uri"] == ["'none'"]
    assert policy["frame-ancestors"] == ["'none'"]


def test_the_page_has_the_other_headers() -> None:
    headers = _page_headers()

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]

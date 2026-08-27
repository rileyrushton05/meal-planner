"""Tests for how the UI decides which database to talk to."""

from __future__ import annotations

from app.db import DATABASE_URL_ENV_VAR
from ui.services import _configured_url, get_services


def test_environment_variable_beats_streamlit_secrets(monkeypatch):
    """Regression test: a local secrets.toml must not hijack a pinned URL.

    Reading st.secrets writes every top-level secret into os.environ as a
    side effect. When secrets were consulted first, the presence of a
    developer's secrets.toml silently redirected the whole app - including
    this test suite - at the production database.
    """
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "sqlite:///pinned.db")

    # None means "defer to Database", which reads the environment variable.
    assert _configured_url() is None


def test_services_use_the_test_database_not_production(db):
    """The autouse db fixture must be what the UI actually connects to."""
    services = get_services()

    assert services.db.url == db.url
    assert services.db.is_sqlite or "test" in services.db.url

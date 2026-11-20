"""What a deployment's cold start loads.

Every visit after a quiet spell waits for the function to import the app,
so modules only some requests need are imported when first used. These
tests run the entry point in a fresh interpreter, as Vercel does, and fail
if one of them creeps back into the import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from api_client import api_client

ROOT = Path(__file__).resolve().parent.parent

#: Each is loaded only by the request (or local server start) that uses it.
LOADED_ON_FIRST_USE = {
    "alembic": "migrations, which never run on Vercel",
    "app.migrations": "migrations, which never run on Vercel",
    "app.jobs": "the scheduled jobs, run from CI",
    "httpx": "fetching a recipe page, only for an import",
    "app.importing": "importing a recipe from a link",
}


@pytest.fixture(scope="module")
def cold_start(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess:
    database = tmp_path_factory.mktemp("startup") / "startup.db"
    script = (
        "import json, sys\nimport api.index\nprint(json.dumps(sorted(sys.modules)))\n"
    )
    env = {
        **os.environ,
        "MEAL_PLANNER_DB_URL": f"sqlite:///{database}",
        "MEAL_PLANNER_LOG_FORMAT": "json",
        # As deployed: on Vercel, with error tracking configured.
        "VERCEL": "1",
        "SENTRY_DSN": "https://public@sentry.invalid/1",
    }
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


@pytest.mark.parametrize("module", sorted(LOADED_ON_FIRST_USE))
def test_a_cold_start_does_not_load(cold_start, module):
    loaded = set(json.loads(cold_start.stdout))

    assert module not in loaded, (
        f"{module} is imported at startup, though only {LOADED_ON_FIRST_USE[module]} "
        "needs it; import it where it is used."
    )


def test_a_cold_start_says_how_long_the_import_took(cold_start):
    events = [
        json.loads(line)
        for line in cold_start.stderr.splitlines()
        if line.startswith("{")
    ]

    (started,) = [e for e in events if e.get("event") == "cold_start"]
    assert started["logger"] == "meal_planner.startup"
    assert started["import_ms"] > 0


def test_a_recipe_import_still_loads_what_it_needs(db, monkeypatch):
    """Deferred, not dropped: the route still reaches the importer."""
    from app import importing
    from app.exceptions import RecipeImportError

    def refuse(*_args, **_kwargs):
        raise RecipeImportError("That page could not be reached.")

    monkeypatch.setattr(importing, "import_recipe", refuse)

    with api_client() as client:
        response = client.post(
            "/api/recipes/import", json={"url": "https://recipes.example/ragu"}
        )

    assert response.status_code == 422
    assert "could not be reached" in response.text

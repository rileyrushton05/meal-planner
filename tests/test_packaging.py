"""The dependency lists are duplicated; this stops them drifting apart.

pyproject.toml is the source of truth, but two requirements files exist for
reasons the deployment forces: Vercel's Python builder installs the function's
dependencies from a requirements.txt, and with a custom buildCommand it needed
one next to the entrypoint as well. When those fell out of step the deployed
function crashed with ModuleNotFoundError, so the agreement is worth a test.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REQUIREMENTS = [
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "api" / "requirements.txt",
]


def _pinned(lines: list[str]) -> set[str]:
    """The `name==version` entries, ignoring comments, blanks and -r includes."""
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    }


def _declared_runtime_dependencies() -> set[str]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    project = pyproject["project"]
    # The API extra is runtime too: it is what the serverless function imports.
    return set(project["dependencies"]) | set(project["optional-dependencies"]["api"])


@pytest.mark.parametrize(
    "requirements", RUNTIME_REQUIREMENTS, ids=lambda p: str(p.name)
)
def test_requirements_files_cover_every_runtime_dependency(requirements: Path):
    declared = _declared_runtime_dependencies()
    listed = _pinned(requirements.read_text().splitlines())

    # uvicorn only serves the app locally; the serverless runtime supplies it.
    missing = {dep for dep in declared if not dep.startswith("uvicorn")} - listed

    assert not missing, (
        f"{requirements.relative_to(PROJECT_ROOT)} is missing {sorted(missing)}. "
        "Deploying without these is how the function crashed on import before."
    )


def test_the_two_requirements_files_agree():
    first, second = (_pinned(p.read_text().splitlines()) for p in RUNTIME_REQUIREMENTS)

    assert first == second, (
        "requirements.txt and api/requirements.txt have drifted; the deployed "
        f"function would install a different set. Difference: {first ^ second}"
    )


def test_every_pin_is_exact():
    """A floating version means the deployment can change without a commit."""
    for path in RUNTIME_REQUIREMENTS:
        for entry in _pinned(path.read_text().splitlines()):
            assert "==" in entry, f"{path.name} pins {entry!r} loosely"

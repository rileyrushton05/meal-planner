import pytest
from sqlmodel import SQLModel, create_engine

import app.db as db


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Point app.db.engine at a throwaway SQLite file for every test,
    so tests never touch the real data/data.db."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db, "engine", test_engine)
    yield

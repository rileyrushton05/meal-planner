import os
from pathlib import Path

from sqlmodel import SQLModel, create_engine, Session

# Imported for its side effect of registering the table models with
# SQLModel.metadata before create_all() runs below - required even
# though `models` is never referenced directly.
from app import models

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR / 'data.db'}"

SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"
engine = create_engine(DATABASE_URL, echo=SQL_ECHO)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)


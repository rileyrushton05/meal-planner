"""Create the database and tables without launching the UI.

Useful after deleting data/data.db, or to check the schema applies cleanly.
"""

from app.db import Database


def main() -> None:
    database = Database()
    database.create_tables()
    print("Database and tables created successfully!")


if __name__ == "__main__":
    main()

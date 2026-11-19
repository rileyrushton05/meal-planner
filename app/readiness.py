"""Read-only checks of the database contract this application needs."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Connection,
    Engine,
    Table,
    and_,
    case,
    func,
    literal,
    or_,
    select,
    true,
    union_all,
)
from sqlmodel import SQLModel

# Register the application's tables, as app.db does before create_tables().
from app import models  # noqa: F401

_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")


def check_database_ready(engine: Engine) -> None:
    """Check the modeled schema and the current connection's privileges.

    Probes fetch no application rows, change no data, and need no access to
    migration history. Additional columns from newer migrations are allowed.
    """
    tables = SQLModel.metadata.sorted_tables
    postgres = engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        if postgres:
            _set_probe_timeouts(connection)
        _check_schema(connection, tables)
        if postgres:
            _check_postgres_permissions(connection, tables)


def _check_schema(connection: Connection, tables: Sequence[Table]) -> None:
    # Each subquery names every modeled column but returns no rows. UNION
    # batches the checks into one round trip, even on a remote database.
    probes = [
        select(literal(1)).select_from(select(table).limit(0).subquery())
        for table in tables
    ]
    connection.execute(union_all(*probes)).close()


def _set_probe_timeouts(connection: Connection) -> None:
    # Local to this transaction; returning the connection to the pool rolls
    # them back, including when the probe fails.
    connection.execute(
        select(
            func.set_config("statement_timeout", "5s", True),
            func.set_config("lock_timeout", "2s", True),
        )
    ).close()


def _check_postgres_permissions(
    connection: Connection, tables: Sequence[Table]
) -> None:
    privileges: list[ColumnElement[bool]] = [
        func.has_table_privilege(table.fullname, privilege, type_=Boolean)
        for table in tables
        for privilege in _TABLE_PRIVILEGES
    ]
    for table in tables:
        column = table.autoincrement_column
        if column is not None:
            sequence = func.pg_get_serial_sequence(table.fullname, column.name)
            privileges.append(
                func.has_sequence_privilege(sequence, "USAGE", type_=Boolean)
            )

    row_security_active = or_(
        *(func.row_security_active(table.fullname, type_=Boolean) for table in tables)
    )
    privileges.append(
        case(
            (
                row_security_active,
                func.has_function_privilege(
                    "current_app_user_id()", "EXECUTE", type_=Boolean
                ),
            ),
            else_=true(),
        )
    )
    # NULL (for example, a missing ID sequence) must fail just like false.
    if connection.execute(select(and_(*privileges))).scalar_one() is not True:
        raise RuntimeError("Required database permissions are missing.")

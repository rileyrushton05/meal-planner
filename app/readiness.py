"""Read-only checks of the database contract this application needs."""

from __future__ import annotations

from typing import cast

from sqlalchemy import Engine, literal, select, text, union_all
from sqlmodel import SQLModel

from app.models import ALL_TABLES

_POSTGRES_PERMISSIONS = text(
    """
    SELECT
        (SELECT bool_and(has_table_privilege(table_name, privilege))
         FROM unnest(CAST(:tables AS text[])) AS tables(table_name)
         CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
             AS privileges(privilege))
        AND
        (SELECT bool_and(COALESCE(has_sequence_privilege(
             pg_get_serial_sequence(table_name, 'id'), 'USAGE'), false))
         FROM unnest(CAST(:id_tables AS text[])) AS tables(table_name))
        AND
        CASE WHEN row_security_active('meals')
            THEN has_function_privilege('current_app_user_id()', 'EXECUTE')
            ELSE true
        END
    """
)


def check_database_ready(engine: Engine) -> None:
    """Raise if required tables, columns or privileges are missing.

    Select the modeled columns with LIMIT 0: the database checks them,
    without reading anyone's data or changing rows or sequence values.
    A single UNION combines the probes into one round trip.

    Check the contract rather than an exact migration revision. Additive
    migrations remain compatible, and the restricted runtime role does not
    need access to Alembic's version table (which it deliberately lacks).
    """
    tables = [
        SQLModel.metadata.tables[cast(str, model.__tablename__)] for model in ALL_TABLES
    ]
    probes = [
        select(literal(1)).select_from(select(table).limit(0).subquery())
        for table in tables
    ]
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            # Transaction-local, so a pooled connection cannot carry these
            # limits into an application request. Also bound DDL lock waits.
            connection.execute(
                text(
                    "SELECT set_config('statement_timeout', '5000', true), "
                    "set_config('lock_timeout', '2000', true)"
                )
            )
        connection.execute(union_all(*probes)).close()
        if engine.dialect.name == "postgresql":
            allowed = connection.execute(
                _POSTGRES_PERMISSIONS,
                {
                    "tables": [table.name for table in tables],
                    "id_tables": [table.name for table in tables if "id" in table.c],
                },
            ).scalar_one()
            if not allowed:
                raise RuntimeError("Required database permissions are missing.")

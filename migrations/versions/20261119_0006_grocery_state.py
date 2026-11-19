"""What a person does to their grocery list, kept with their account.

Revision ID: 20261119_0006
Revises: 20261119_0005
Create Date: 2026-11-19

What changes: four new tables, all one user's own.

- `grocery_checks`: a line of one week's list ticked off (in the basket) or
  marked as already at home, keyed by the line's name and unit. Until now a
  tick lived in one browser's storage, so it was lost on another device.
- `grocery_extras`: things on one week's list that no meal needs.
- `grocery_usuals`: things bought most weeks, added to a list in one go.
- `grocery_settings`: one row per person who has changed the order of the
  aisles; no row means the default order.

In Postgres each gets the same row-level security as the other tables that
hold someone's data: the runtime role sees and writes only the declared
user's rows. An extra may also name a catalogue item, which is shared
reference data, so its policy needs nothing further.

Additive: new tables only, so code already running is unaffected. Nothing is
copied from browsers' storage: ticks made before this start empty once.

How the upgrade can fail: it cannot, short of the tables already existing.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "20261119_0006"
down_revision = "20261119_0005"
branch_labels = None
depends_on = None

ROLE = "meal_planner_app"
_OWN_ROWS = "user_id = current_app_user_id()"
_TABLES = ("grocery_checks", "grocery_extras", "grocery_usuals", "grocery_settings")
_SEQUENCES = ("grocery_extras_id_seq", "grocery_usuals_id_seq")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def _owner(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        name=op.f(f"fk_{table}_user_id_users"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "grocery_checks",
        *_timestamps(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("item_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("state", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.CheckConstraint(
            "state IN ('basket', 'have')", name=op.f("ck_grocery_checks_state_known")
        ),
        _owner("grocery_checks"),
        sa.PrimaryKeyConstraint(
            "user_id", "week_start_date", "item_key", name=op.f("pk_grocery_checks")
        ),
    )

    op.create_table(
        "grocery_extras",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column(
            "unit",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="",
            nullable=False,
        ),
        sa.Column("catalog_item_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "qty IS NULL OR qty > 0", name=op.f("ck_grocery_extras_qty_positive")
        ),
        _owner("grocery_extras"),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"],
            ["catalog_items.id"],
            name=op.f("fk_grocery_extras_catalog_item_id_catalog_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grocery_extras")),
    )
    op.create_index(
        op.f("ix_grocery_extras_catalog_item_id"),
        "grocery_extras",
        ["catalog_item_id"],
    )
    op.create_index(
        "uq_grocery_extras_user_id_week_start_date_lower_name",
        "grocery_extras",
        ["user_id", "week_start_date", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "grocery_usuals",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column(
            "unit",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="",
            nullable=False,
        ),
        sa.CheckConstraint(
            "qty IS NULL OR qty > 0", name=op.f("ck_grocery_usuals_qty_positive")
        ),
        _owner("grocery_usuals"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grocery_usuals")),
    )
    op.create_index(
        "uq_grocery_usuals_user_id_lower_name",
        "grocery_usuals",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "grocery_settings",
        *_timestamps(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("aisle_order", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        _owner("grocery_settings"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_grocery_settings")),
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_own_rows ON {table} FOR ALL TO {ROLE} "
                f"USING ({_OWN_ROWS}) WITH CHECK ({_OWN_ROWS})"
            )
        for sequence in _SEQUENCES:
            op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {ROLE}")


def downgrade() -> None:
    # Dropping a table drops its grants, policy and sequence with it.
    op.drop_table("grocery_settings")
    op.drop_index("uq_grocery_usuals_user_id_lower_name", table_name="grocery_usuals")
    op.drop_table("grocery_usuals")
    op.drop_index(
        "uq_grocery_extras_user_id_week_start_date_lower_name",
        table_name="grocery_extras",
    )
    op.drop_index(
        op.f("ix_grocery_extras_catalog_item_id"), table_name="grocery_extras"
    )
    op.drop_table("grocery_extras")
    op.drop_table("grocery_checks")

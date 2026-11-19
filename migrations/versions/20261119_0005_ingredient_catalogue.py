"""The ingredient catalogue: common items a person's ingredients link to.

Revision ID: 20261119_0005
Revises: 20261118_0004
Create Date: 2026-11-19

What changes: two new tables, `catalog_items` (one row per common grocery
item, with its aisle, how it is measured and the typical weight of one) and
`catalog_aliases` (every spelling that means an item, its own name
included), and a nullable `ingredients.catalog_item_id` linking a person's
ingredient to the item it is. The tables start empty: `python -m app.jobs
sync-catalog` loads them from app/catalog.csv and links existing
ingredients. Additive, so safe for code already running.

In Postgres the runtime role may only read the catalogue, never change it:
it is shared reference data, written by the sync job as the owner. It
belongs to no user, so it has no row-level security policy. The new column
on `ingredients` is covered by that table's existing grants and policy.

Also a repair, on SQLite only. To alter a table there, Alembic rebuilds it
("batch mode"), and the rebuild silently drops expression indexes, which it
cannot reflect. Migration 20261118_0004 lost `uq_users_lower_email` that
way, and adding the column here would lose
`uq_ingredients_user_id_lower_name`, so both are recreated. Postgres alters
tables in place and keeps them; tests/test_migrations.py now checks that
every index the models declare survives the migrations.

How the upgrade can fail: on SQLite, if a database that lost the email index
has since stored two emails differing only in case. Postgres: it cannot,
short of the tables already existing.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "20261119_0005"
down_revision = "20261118_0004"
branch_labels = None
depends_on = None

ROLE = "meal_planner_app"


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


def upgrade() -> None:
    op.create_table(
        "catalog_items",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("measure", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("each_grams", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "category IN ('produce', 'meat', 'dairy', 'bakery', 'pantry', 'frozen')",
            name=op.f("ck_catalog_items_category_known"),
        ),
        sa.CheckConstraint(
            "measure IN ('mass', 'volume', 'count')",
            name=op.f("ck_catalog_items_measure_known"),
        ),
        sa.CheckConstraint(
            "each_grams IS NULL OR each_grams > 0",
            name=op.f("ck_catalog_items_each_grams_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_items")),
        sa.UniqueConstraint("name_key", name=op.f("uq_catalog_items_name_key")),
    )
    op.create_table(
        "catalog_aliases",
        *_timestamps(),
        sa.Column("alias_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("catalog_item_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"],
            ["catalog_items.id"],
            name=op.f("fk_catalog_aliases_catalog_item_id_catalog_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alias_key", name=op.f("pk_catalog_aliases")),
    )
    op.create_index(
        op.f("ix_catalog_aliases_catalog_item_id"),
        "catalog_aliases",
        ["catalog_item_id"],
    )

    with op.batch_alter_table("ingredients") as batch:
        batch.add_column(sa.Column("catalog_item_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_ingredients_catalog_item_id_catalog_items"),
            "catalog_items",
            ["catalog_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_ingredients_catalog_item_id"), ["catalog_item_id"])

    _restore_expression_indexes()

    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"GRANT SELECT ON catalog_items, catalog_aliases TO {ROLE}")


def downgrade() -> None:
    with op.batch_alter_table("ingredients") as batch:
        batch.drop_index(op.f("ix_ingredients_catalog_item_id"))
        batch.drop_constraint(
            op.f("fk_ingredients_catalog_item_id_catalog_items"), type_="foreignkey"
        )
        batch.drop_column("catalog_item_id")
    _restore_expression_indexes()
    # Dropping the tables drops their grants with them.
    op.drop_index(
        op.f("ix_catalog_aliases_catalog_item_id"), table_name="catalog_aliases"
    )
    op.drop_table("catalog_aliases")
    op.drop_table("catalog_items")


def _restore_expression_indexes() -> None:
    """Recreate the case-insensitive unique indexes a SQLite table rebuild
    drops (see the module docstring). A no-op where they already exist."""
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ingredients_user_id_lower_name "
        "ON ingredients (user_id, lower(name))"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_lower_email ON users (lower(email))"
    )

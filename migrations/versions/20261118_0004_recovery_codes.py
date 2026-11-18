"""Recovery codes: how an account gets back in after a forgotten password.

Revision ID: 20261118_0004
Revises: 20261117_0003
Create Date: 2026-11-18

What changes: `users.recovery_code_hash`, the SHA-256 of a code shown to
the person once and never stored, and a check that only an account with a
login can have one. Additive and nullable, so safe for code already
running: existing accounts simply have no code until they make one.

`users` has no row-level security policy, and the runtime role's grants on
it cover new columns, so nothing changes for the role.

How the upgrade can fail: it cannot, short of the column already existing.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "20261118_0004"
down_revision = "20261117_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "recovery_code_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True
            )
        )
        batch.create_check_constraint(
            op.f("ck_users_recovery_code_needs_login"),
            "recovery_code_hash IS NULL OR email IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("ck_users_recovery_code_needs_login"), type_="check")
        batch.drop_column("recovery_code_hash")

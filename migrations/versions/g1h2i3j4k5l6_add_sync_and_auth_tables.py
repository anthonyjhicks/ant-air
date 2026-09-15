"""Add sync revision columns, soft delete, sync_state and api_user tables.

Revision ID: g1h2i3j4k5l6
Revises: f6a7b8c9d0e1
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "g1h2i3j4k5l6"
down_revision = "a6489338417a"
branch_labels = None
depends_on = None


def upgrade():
    # --- New tables ---
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("current_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name="sync_state_singleton"),
    )

    op.create_table(
        "api_user",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login", sa.DateTime()),
    )

    # --- Add sync_revision and deleted_at to existing tables ---
    with op.batch_alter_table("flight") as batch_op:
        batch_op.add_column(sa.Column("sync_revision", sa.BigInteger(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime()))

    with op.batch_alter_table("trip") as batch_op:
        batch_op.add_column(sa.Column("sync_revision", sa.BigInteger(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime()))

    with op.batch_alter_table("trip_leg") as batch_op:
        batch_op.add_column(sa.Column("sync_revision", sa.BigInteger(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime()))

    with op.batch_alter_table("aircraft") as batch_op:
        batch_op.add_column(sa.Column("sync_revision", sa.BigInteger(), nullable=False, server_default="0"))

    with op.batch_alter_table("achievement_badge") as batch_op:
        batch_op.add_column(sa.Column("sync_revision", sa.BigInteger(), nullable=False, server_default="0"))

    # Insert the singleton sync_state row
    op.execute("INSERT INTO sync_state (id, current_revision) VALUES (1, 0)")


def downgrade():
    with op.batch_alter_table("achievement_badge") as batch_op:
        batch_op.drop_column("sync_revision")

    with op.batch_alter_table("aircraft") as batch_op:
        batch_op.drop_column("sync_revision")

    with op.batch_alter_table("trip_leg") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("sync_revision")

    with op.batch_alter_table("trip") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("sync_revision")

    with op.batch_alter_table("flight") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("sync_revision")

    op.drop_table("api_user")
    op.drop_table("sync_state")

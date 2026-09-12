"""Create games table."""

from alembic import op
import sqlalchemy as sa


revision = "20260901_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_color", sa.String(length=5), nullable=False),
        sa.Column("white_player", sa.String(length=100), nullable=False),
        sa.Column("black_player", sa.String(length=100), nullable=False),
        sa.Column("result", sa.String(length=7), nullable=False),
        sa.Column("raw_pgn", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("games")

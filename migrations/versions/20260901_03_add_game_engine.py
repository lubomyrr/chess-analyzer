"""Add the selected analysis engine to games."""

from alembic import op
import sqlalchemy as sa


revision = "20260901_03"
down_revision = "20260901_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column(
            "engine",
            sa.String(length=20),
            server_default="stockfish",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("games", "engine")

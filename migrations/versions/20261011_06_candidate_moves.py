"""Store the top Stockfish candidates for board arrows."""

from alembic import op
import sqlalchemy as sa

revision = "20261011_06"
down_revision = "20260902_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game_moves", sa.Column("candidate_moves", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_moves", "candidate_moves")

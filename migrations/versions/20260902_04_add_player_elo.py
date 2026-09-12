"""Store player Elo ratings."""

from alembic import op
import sqlalchemy as sa


revision = "20260902_04"
down_revision = "20260901_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("white_elo", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("black_elo", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE games
        SET white_elo = substring(raw_pgn from '\\[WhiteElo "([0-9]+)"\\]')::integer,
            black_elo = substring(raw_pgn from '\\[BlackElo "([0-9]+)"\\]')::integer
        """
    )


def downgrade() -> None:
    op.drop_column("games", "black_elo")
    op.drop_column("games", "white_elo")

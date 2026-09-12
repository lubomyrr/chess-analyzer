"""Normalize move classifications and retire active RubiChess jobs."""

from alembic import op


revision = "20260902_05"
down_revision = "20260902_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE game_moves
        SET classification = CASE
            WHEN centipawn_loss <= 15 THEN 'best'
            ELSE 'good'
        END
        WHERE classification = 'normal'
        """
    )
    op.execute(
        """
        UPDATE games
        SET engine = 'stockfish',
            status = 'failed',
            error_message = 'Re-run analysis after the Stockfish-only upgrade.'
        WHERE engine = 'rubichess' AND status IN ('queued', 'analyzing')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE game_moves
        SET classification = 'normal'
        WHERE classification IN ('best', 'good')
        """
    )

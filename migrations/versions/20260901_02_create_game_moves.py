"""Create analyzed game moves."""

from alembic import op
import sqlalchemy as sa


revision = "20260901_02"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_moves",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("move_number", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("uci_move", sa.String(length=5), nullable=False),
        sa.Column("san_move", sa.String(length=30), nullable=False),
        sa.Column("fen_before", sa.Text(), nullable=False),
        sa.Column("fen_after", sa.Text(), nullable=False),
        sa.Column("evaluation_before", sa.Integer(), nullable=True),
        sa.Column("evaluation_after", sa.Integer(), nullable=True),
        sa.Column("centipawn_loss", sa.Integer(), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=True),
        sa.Column("best_move", sa.String(length=5), nullable=True),
        sa.Column("principal_variation", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "ply", name="uq_game_moves_game_id_ply"),
    )
    op.create_index("ix_game_moves_game_id", "game_moves", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_game_moves_game_id", table_name="game_moves")
    op.drop_table("game_moves")

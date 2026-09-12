from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GameMove(Base):
    __tablename__ = "game_moves"
    __table_args__ = (
        UniqueConstraint("game_id", "ply", name="uq_game_moves_game_id_ply"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        index=True,
    )
    ply: Mapped[int]
    move_number: Mapped[int]
    side: Mapped[str] = mapped_column(String(5))
    uci_move: Mapped[str] = mapped_column(String(5))
    san_move: Mapped[str] = mapped_column(String(30))
    fen_before: Mapped[str] = mapped_column(Text)
    fen_after: Mapped[str] = mapped_column(Text)
    evaluation_before: Mapped[int | None]
    evaluation_after: Mapped[int | None]
    centipawn_loss: Mapped[int | None]
    classification: Mapped[str | None] = mapped_column(String(20))
    best_move: Mapped[str | None] = mapped_column(String(5))
    principal_variation: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

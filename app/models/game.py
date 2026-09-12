from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_color: Mapped[str] = mapped_column(String(5))
    engine: Mapped[str] = mapped_column(
        String(20),
        default="stockfish",
        server_default="stockfish",
    )
    white_player: Mapped[str] = mapped_column(String(100))
    black_player: Mapped[str] = mapped_column(String(100))
    white_elo: Mapped[int | None] = mapped_column(Integer)
    black_elo: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(7))
    raw_pgn: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        default="queued",
        server_default="queued",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

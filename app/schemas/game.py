from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_color: str
    engine: str
    white_player: str
    black_player: str
    white_elo: int | None
    black_elo: int | None
    result: str
    status: str
    error_message: str | None
    played_at: datetime | None
    created_at: datetime
    analyzed_at: datetime | None


class GameMoveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ply: int
    move_number: int
    side: str
    uci_move: str
    san_move: str
    fen_before: str
    fen_after: str
    evaluation_before: int | None
    evaluation_after: int | None
    centipawn_loss: int | None
    classification: str | None
    best_move: str | None
    principal_variation: list[str] | None


class PlayerStatisticsResponse(BaseModel):
    color: str
    player: str
    accuracy: float | None
    moves: int
    best: int
    good: int
    inaccuracies: int
    mistakes: int
    blunders: int


class GameAnalysisResponse(BaseModel):
    game_id: int
    status: str
    engine: str
    white_stats: PlayerStatisticsResponse
    black_stats: PlayerStatisticsResponse
    moves: list[GameMoveResponse]

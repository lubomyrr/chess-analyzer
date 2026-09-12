from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.game_move import GameMove
from app.services.pgn_parser import ParsedGame


def create_game(
    database: Session,
    parsed_game: ParsedGame,
    raw_pgn: str,
    user_color: str,
) -> Game:
    game = Game(
        user_color=user_color,
        engine="stockfish",
        white_player=parsed_game.white_player,
        black_player=parsed_game.black_player,
        white_elo=parsed_game.white_elo,
        black_elo=parsed_game.black_elo,
        result=parsed_game.result,
        raw_pgn=raw_pgn,
        played_at=parsed_game.played_at,
        status="queued",
    )
    database.add(game)
    database.commit()
    database.refresh(game)
    return game


def get_games(database: Session) -> list[Game]:
    statement = select(Game).order_by(Game.created_at.desc())
    return list(database.scalars(statement))


def get_game(database: Session, game_id: int) -> Game | None:
    return database.get(Game, game_id)


def get_game_for_update(database: Session, game_id: int) -> Game | None:
    statement = select(Game).where(Game.id == game_id).with_for_update()
    return database.scalar(statement)


def delete_game(database: Session, game: Game) -> None:
    database.delete(game)
    database.commit()


def get_game_moves(database: Session, game_id: int) -> list[GameMove]:
    statement = (
        select(GameMove)
        .where(GameMove.game_id == game_id)
        .order_by(GameMove.ply)
    )
    return list(database.scalars(statement))

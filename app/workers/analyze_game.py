from datetime import datetime, timezone

import chess
import chess.engine
from sqlalchemy import delete

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.game import Game
from app.models.game_move import GameMove
from app.services.chess_analysis import analyze_moves
from app.services.pgn_parser import parse_pgn


@celery_app.task(name="games.analyze", reject_on_worker_lost=True)
def analyze_game_task(game_id: int) -> None:
    with SessionLocal() as database:
        game = database.get(Game, game_id)
        if game is None or game.status == "completed":
            return

        game.status = "analyzing"
        game.engine = "stockfish"
        game.error_message = None
        database.commit()

        engine: chess.engine.SimpleEngine | None = None

        try:
            parsed_game = parse_pgn(game.raw_pgn)
            engine = chess.engine.SimpleEngine.popen_uci(
                settings.stockfish_path,
                timeout=settings.stockfish_timeout_seconds,
            )
            engine_options = {}
            if "Threads" in engine.options:
                engine_options["Threads"] = settings.stockfish_threads
            if "Hash" in engine.options:
                engine_options["Hash"] = settings.stockfish_hash_mb
            if engine_options:
                engine.configure(engine_options)

            board = chess.Board(parsed_game.starting_fen)
            played_moves = (
                chess.Move.from_uci(parsed_move.uci_move)
                for parsed_move in parsed_game.moves
            )
            analyses = analyze_moves(
                engine=engine,
                board=board,
                played_moves=played_moves,
                depth=settings.stockfish_depth,
                pv_length=settings.analysis_pv_length,
            )
            game_moves = [
                GameMove(
                    game_id=game.id,
                    ply=parsed_move.ply,
                    move_number=parsed_move.move_number,
                    side=parsed_move.side,
                    uci_move=parsed_move.uci_move,
                    san_move=parsed_move.san_move,
                    fen_before=parsed_move.fen_before,
                    fen_after=parsed_move.fen_after,
                    evaluation_before=analysis.evaluation_before,
                    evaluation_after=analysis.evaluation_after,
                    centipawn_loss=analysis.centipawn_loss,
                    classification=analysis.classification,
                    best_move=analysis.best_move,
                    principal_variation=analysis.principal_variation,
                )
                for parsed_move, analysis in zip(
                    parsed_game.moves,
                    analyses,
                    strict=True,
                )
            ]

            database.execute(
                delete(GameMove).where(GameMove.game_id == game.id)
            )
            database.add_all(game_moves)
            game.status = "completed"
            game.analyzed_at = datetime.now(timezone.utc)
            database.commit()
        except Exception as error:
            database.rollback()
            failed_game = database.get(Game, game_id)
            if failed_game is not None:
                failed_game.status = "failed"
                failed_game.error_message = str(error)[:1000]
                database.commit()
            raise
        finally:
            if engine is not None:
                try:
                    engine.quit()
                except (chess.engine.EngineError, OSError, TimeoutError):
                    pass

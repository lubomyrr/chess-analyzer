from datetime import datetime, timezone
import os
from time import monotonic

from sqlalchemy import delete

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.game import Game
from app.models.game_move import GameMove
from app.services.chess_analysis import analyze_game_parallel
from app.services.pgn_parser import parse_pgn


def engine_thread_count(configured: int) -> int:
    if configured > 0:
        return configured
    available = (len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
                 else os.cpu_count() or 1)
    return min(8, max(1, available - 2 if available > 4 else available))


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

        try:
            parsed_game = parse_pgn(game.raw_pgn)
            # Publish completed moves while the remaining positions are searched.
            database.execute(delete(GameMove).where(GameMove.game_id == game.id))
            database.commit()
            last_publish = monotonic()
            analyses = analyze_game_parallel(
                parsed_game,
                engine_path=settings.stockfish_path,
                depth=settings.stockfish_depth,
                pv_length=settings.analysis_pv_length,
                cpu_budget=engine_thread_count(settings.stockfish_threads),
                hash_mb=settings.stockfish_hash_mb,
                timeout=settings.stockfish_timeout_seconds,
                use_cache=True,
            )
            for parsed_move, analysis in zip(parsed_game.moves, analyses, strict=True):
                database.add(GameMove(
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
                    candidate_moves=analysis.candidate_moves,
                ))
                now = monotonic()
                if parsed_move.ply == 1 or now - last_publish >= 0.25:
                    database.commit()
                    last_publish = now
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

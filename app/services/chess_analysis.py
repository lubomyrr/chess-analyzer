from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import chess
import chess.engine


@dataclass
class MoveAnalysis:
    evaluation_before: int
    evaluation_after: int
    centipawn_loss: int
    classification: str
    best_move: str
    principal_variation: list[str]


def analyze_moves(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    played_moves: Iterable[chess.Move],
    depth: int,
    pv_length: int,
) -> Iterator[MoveAnalysis]:
    """Analyze N moves with N+1 engine calls by reusing adjacent positions."""
    limit = chess.engine.Limit(depth=depth)
    before_info = engine.analyse(board, limit)

    for played_move in played_moves:
        moving_color = board.turn
        board.push(played_move)
        after_info = engine.analyse(board, limit)

        yield _build_move_analysis(
            played_move=played_move,
            moving_color=moving_color,
            before_info=before_info,
            after_info=after_info,
            pv_length=pv_length,
        )
        before_info = after_info


def classify_centipawn_loss(centipawn_loss: int) -> str:
    if centipawn_loss <= 15:
        return "best"
    if centipawn_loss < 50:
        return "good"
    if centipawn_loss < 100:
        return "inaccuracy"
    if centipawn_loss < 200:
        return "mistake"
    return "blunder"


def _build_move_analysis(
    played_move: chess.Move,
    moving_color: chess.Color,
    before_info: chess.engine.InfoDict,
    after_info: chess.engine.InfoDict,
    pv_length: int,
) -> MoveAnalysis:
    # Board evaluation always uses White's point of view so the UI does not
    # change signs after every move.
    evaluation_before = _score_for_color(before_info["score"], chess.WHITE)
    evaluation_after = _score_for_color(after_info["score"], chess.WHITE)

    # Move quality uses the point of view of the player who made the move.
    mover_evaluation_before = _score_for_color(before_info["score"], moving_color)
    mover_evaluation_after = _score_for_color(after_info["score"], moving_color)
    centipawn_loss = max(0, mover_evaluation_before - mover_evaluation_after)

    principal_variation = [
        move.uci() for move in before_info.get("pv", [])[:pv_length]
    ]
    best_move = principal_variation[0] if principal_variation else played_move.uci()

    return MoveAnalysis(
        evaluation_before=evaluation_before,
        evaluation_after=evaluation_after,
        centipawn_loss=centipawn_loss,
        classification=classify_centipawn_loss(centipawn_loss),
        best_move=best_move,
        principal_variation=principal_variation,
    )


def _score_for_color(
    score: chess.engine.PovScore,
    color: chess.Color,
) -> int:
    value = score.pov(color).score(mate_score=100_000)
    if value is None:
        raise ValueError("Stockfish returned an empty score")
    return value

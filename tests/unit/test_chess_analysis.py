import chess
import chess.engine
import pytest

from app.services.chess_analysis import analyze_moves, classify_centipawn_loss


class StubEngine:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.calls = 0

    def analyse(self, board: chess.Board, limit: chess.engine.Limit) -> dict:
        self.calls += 1
        return self.results.pop(0)


def engine_result(score: int, pv: str) -> dict:
    return {
        "score": chess.engine.PovScore(chess.engine.Cp(score), chess.WHITE),
        "pv": [chess.Move.from_uci(pv)],
    }


@pytest.mark.parametrize(
    ("loss", "expected"),
    [
        (0, "best"),
        (15, "best"),
        (16, "good"),
        (49, "good"),
        (50, "inaccuracy"),
        (99, "inaccuracy"),
        (100, "mistake"),
        (199, "mistake"),
        (200, "blunder"),
    ],
)
def test_classify_centipawn_loss(loss: int, expected: str) -> None:
    assert classify_centipawn_loss(loss) == expected


def test_analyze_black_move_keeps_board_score_from_white_view() -> None:
    board = chess.Board()
    board.push_uci("e2e4")
    engine = StubEngine(
        [
            engine_result(30, "e7e5"),
            engine_result(130, "g1f3"),
        ]
    )

    analysis = next(
        analyze_moves(
            engine=engine,
            board=board,
            played_moves=[chess.Move.from_uci("e7e5")],
            depth=1,
            pv_length=1,
        )
    )

    assert analysis.evaluation_before == 30
    assert analysis.evaluation_after == 130
    assert analysis.centipawn_loss == 100
    assert analysis.classification == "mistake"
    assert analysis.best_move == "e7e5"


def test_analyze_moves_reuses_intermediate_position() -> None:
    engine = StubEngine(
        [
            engine_result(20, "e2e4"),
            engine_result(15, "e7e5"),
            engine_result(25, "g1f3"),
        ]
    )

    analyses = list(
        analyze_moves(
            engine=engine,
            board=chess.Board(),
            played_moves=[
                chess.Move.from_uci("e2e4"),
                chess.Move.from_uci("e7e5"),
            ],
            depth=1,
            pv_length=1,
        )
    )

    assert len(analyses) == 2
    assert engine.calls == 3

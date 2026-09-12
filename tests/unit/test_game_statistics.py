from types import SimpleNamespace

from app.services.game_statistics import (
    calculate_player_statistics,
    move_accuracy,
)


def test_move_accuracy_stays_between_zero_and_one_hundred() -> None:
    assert move_accuracy(0) == 100.0
    assert move_accuracy(100) < 100
    assert move_accuracy(100_000) == 0.0


def test_calculate_player_statistics_uses_only_selected_color() -> None:
    moves = [
        SimpleNamespace(
            side="white",
            centipawn_loss=0,
            classification="best",
        ),
        SimpleNamespace(
            side="black",
            centipawn_loss=200,
            classification="blunder",
        ),
        SimpleNamespace(
            side="white",
            centipawn_loss=100,
            classification="mistake",
        ),
    ]

    statistics = calculate_player_statistics(moves, "white", "White Player")

    assert statistics["player"] == "White Player"
    assert statistics["moves"] == 2
    assert statistics["best"] == 1
    assert statistics["mistakes"] == 1
    assert statistics["blunders"] == 0
    assert statistics["accuracy"] == 83.5

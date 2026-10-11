from math import exp

from app.models.game_move import GameMove
from app.services.move_quality import CLASSIFICATIONS, expected_points


def move_accuracy(centipawn_loss: int, evaluation_before: int | None = None,
                  evaluation_after: int | None = None, side: str = "white") -> float:
    if evaluation_before is None or evaluation_after is None:
        accuracy = 100 * exp(-max(0, centipawn_loss) / 250)
    else:
        sign = 1 if side == "white" else -1
        loss = max(0, expected_points(sign * evaluation_before)
                   - expected_points(sign * evaluation_after))
        accuracy = 100 * exp(-5 * loss)
    return round(max(0, min(100, accuracy)), 1)


def calculate_player_statistics(
    moves: list[GameMove],
    color: str,
    player: str,
) -> dict[str, str | int | float | None]:
    move_count = 0
    accuracy_total = 0.0
    rated_count = 0
    classifications = dict.fromkeys(CLASSIFICATIONS, 0)

    for move in moves:
        if move.side != color:
            continue
        move_count += 1
        if move.centipawn_loss is None:
            continue
        rated_count += 1
        accuracy_total += move_accuracy(
            move.centipawn_loss, getattr(move, "evaluation_before", None),
            getattr(move, "evaluation_after", None), move.side,
        )
        if move.classification in classifications:
            classifications[move.classification] += 1

    return {
        "color": color,
        "player": player,
        "accuracy": round(accuracy_total / rated_count, 1)
        if rated_count
        else None,
        "moves": move_count,
        "brilliant": classifications["brilliant"],
        "great": classifications["great"],
        "book": classifications["book"],
        "excellent": classifications["excellent"],
        "miss": classifications["miss"],
        "best": classifications["best"],
        "good": classifications["good"],
        "inaccuracies": classifications["inaccuracy"],
        "mistakes": classifications["mistake"],
        "blunders": classifications["blunder"],
    }

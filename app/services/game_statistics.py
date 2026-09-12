from math import exp

from app.models.game_move import GameMove


def move_accuracy(centipawn_loss: int) -> float:
    """Convert centipawn loss into a simple 0-100 accuracy score."""
    accuracy = 100 * exp(-max(0, centipawn_loss) / 250)
    return round(max(0, min(100, accuracy)), 1)


def calculate_player_statistics(
    moves: list[GameMove],
    color: str,
    player: str,
) -> dict[str, str | int | float | None]:
    move_count = 0
    accuracy_total = 0.0
    rated_count = 0
    classifications = {
        "best": 0,
        "good": 0,
        "inaccuracy": 0,
        "mistake": 0,
        "blunder": 0,
    }

    for move in moves:
        if move.side != color:
            continue
        move_count += 1
        if move.centipawn_loss is None:
            continue
        rated_count += 1
        accuracy_total += move_accuracy(move.centipawn_loss)
        if move.classification in classifications:
            classifications[move.classification] += 1

    return {
        "color": color,
        "player": player,
        "accuracy": round(accuracy_total / rated_count, 1)
        if rated_count
        else None,
        "moves": move_count,
        "best": classifications["best"],
        "good": classifications["good"],
        "inaccuracies": classifications["inaccuracy"],
        "mistakes": classifications["mistake"],
        "blunders": classifications["blunder"],
    }

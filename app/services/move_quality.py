from math import exp

CLASSIFICATIONS = (
    "brilliant", "great", "book", "best", "excellent", "good",
    "inaccuracy", "mistake", "miss", "blunder",
)

EQUAL_POSITION_CP = 75
WINNING_POSITION_CP = 200
GREAT_ALTERNATIVE_LOSS = 0.05


def is_playable_position(centipawns: int) -> bool:
    return centipawns >= -EQUAL_POSITION_CP


def is_great_move(played_cp: int, best_points: float,
                  alternative_points: float | None, *, is_best: bool) -> bool:
    if not is_best or not is_playable_position(played_cp) or alternative_points is None:
        return False
    loss = best_points - alternative_points
    critical = (alternative_points < expected_points(-EQUAL_POSITION_CP)
                or best_points >= expected_points(WINNING_POSITION_CP) > alternative_points
                or loss >= 0.10)
    return (critical and alternative_points < 0.85
            and loss >= GREAT_ALTERNATIVE_LOSS)


def expected_points(centipawns: int) -> float:
    return 1 / (1 + exp(-0.00368208 * max(-10000, min(10000, centipawns))))


def classify_loss(loss: float, *, is_best: bool = False) -> str:
    if is_best:
        return "best"
    if loss < 0.02:
        return "excellent"
    if loss < 0.05:
        return "good"
    if loss < 0.10:
        return "inaccuracy"
    if loss < 0.20:
        return "mistake"
    return "blunder"

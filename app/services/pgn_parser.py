from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import StringIO
import re

import chess.pgn


@dataclass
class ParsedMove:
    ply: int
    move_number: int
    side: str
    uci_move: str
    san_move: str
    fen_before: str
    fen_after: str
    clock_seconds: float | None = None
    thinking_time_seconds: float | None = None


@dataclass
class ParsedGame:
    white_player: str
    black_player: str
    white_elo: int | None
    black_elo: int | None
    result: str
    played_at: datetime | None
    starting_fen: str
    moves: list[ParsedMove]
    initial_clock_seconds: float | None = None


@lru_cache(maxsize=128)
def parse_pgn(raw_pgn: str) -> ParsedGame:
    if not raw_pgn.strip():
        raise ValueError("PGN file is empty")

    pgn_stream = StringIO(raw_pgn)
    game = chess.pgn.read_game(pgn_stream)

    if game is None:
        raise ValueError("PGN does not contain a chess game")

    if game.errors:
        raise ValueError(f"Invalid PGN: {game.errors[0]}")

    second_game = chess.pgn.read_game(pgn_stream)
    if second_game is not None:
        raise ValueError("Upload one game at a time")

    board = game.board()
    starting_fen = board.fen()
    parsed_moves: list[ParsedMove] = []
    control = re.fullmatch(r"(\d+)(?:\+(\d+(?:\.\d+)?))?", game.headers.get("TimeControl", "").strip())
    increment = float(control[2] or 0) if control else None
    initial_clock = (float(control[1]) if control and starting_fen == chess.STARTING_FEN else None)
    previous_clocks = {"white": initial_clock, "black": initial_clock}

    for ply, node in enumerate(game.mainline(), start=1):
        move = node.move
        side = "white" if board.turn == chess.WHITE else "black"
        fen_before = board.fen()
        san_move = board.san(move)
        uci_move = move.uci()
        move_number = board.fullmove_number
        clock = node.clock()
        elapsed = node.emt()
        previous = previous_clocks[side]
        if elapsed is None and clock is not None and previous is not None and increment is not None:
            elapsed = previous + increment - clock
        previous_clocks[side] = clock
        thinking_time = round(elapsed, 3) if elapsed is not None and elapsed >= 0 else None

        board.push(move)

        parsed_moves.append(
            ParsedMove(
                ply=ply,
                move_number=move_number,
                side=side,
                uci_move=uci_move,
                san_move=san_move,
                fen_before=fen_before,
                fen_after=board.fen(),
                clock_seconds=clock,
                thinking_time_seconds=thinking_time,
            )
        )

    if not parsed_moves:
        raise ValueError("PGN does not contain any moves")

    return ParsedGame(
        white_player=game.headers.get("White", "Unknown"),
        black_player=game.headers.get("Black", "Unknown"),
        white_elo=_parse_elo(game.headers.get("WhiteElo")),
        black_elo=_parse_elo(game.headers.get("BlackElo")),
        result=game.headers.get("Result", "*"),
        played_at=_parse_played_at(game.headers),
        starting_fen=starting_fen,
        moves=parsed_moves,
        initial_clock_seconds=initial_clock,
    )


def _parse_elo(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_played_at(headers: chess.pgn.Headers) -> datetime | None:
    date_value = headers.get("UTCDate") or headers.get("Date")
    if not date_value or "?" in date_value:
        return None

    cleaned_date = date_value.strip().replace("-", ".").replace("/", ".")
    parts = cleaned_date.split(".")
    if len(parts) == 3:
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            cleaned_date = f"{year:04d}.{month:02d}.{day:02d}"
        except ValueError:
            return None
    else:
        return None

    time_value = (headers.get("UTCTime") or headers.get("Time") or "00:00:00").strip()
    if "?" in time_value:
        time_value = "00:00:00"

    cleaned_time = time_value.split(".")[0].strip()
    if len(cleaned_time.split(":")) == 2:
        cleaned_time += ":00"

    for time_format in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            parsed = datetime.strptime(f"{cleaned_date} {cleaned_time}", time_format)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        parsed = datetime.strptime(cleaned_date, "%Y.%m.%d")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from collections import Counter, OrderedDict
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import shutil
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock

import chess
import chess.engine

from app.services.move_quality import (
    classify_loss, expected_points, is_great_move, is_playable_position,
)
from app.services.pgn_parser import ParsedGame
from app.services.stockfish_runtime import stockfish_executable

PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
                chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}


@dataclass
class MoveAnalysis:
    evaluation_before: int
    evaluation_after: int
    centipawn_loss: int
    classification: str
    best_move: str
    principal_variation: list[str]
    candidate_moves: list[str] = field(default_factory=list)


_analysis_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = Lock()


@lru_cache(maxsize=8)
def _file_digest(path: str, size: int, modified: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analysis_cache_key(parsed_game: ParsedGame, engine_path: str, depth: int, pv_length: int) -> str:
    paths = [Path(shutil.which(engine_path) or engine_path), Path(__file__),
             Path(classify_loss.__code__.co_filename), Path(__file__).parent / 'data/openings.json']
    fingerprints = []
    for path in paths:
        stat = path.stat()
        fingerprints.append(_file_digest(str(path), stat.st_size, stat.st_mtime_ns))
    payload = [fingerprints, depth, pv_length, parsed_game.starting_fen,
               [move.uci_move for move in parsed_game.moves]]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def analyze_game_parallel(
    parsed_game: ParsedGame, *, engine_path: str, depth: int, pv_length: int,
    cpu_budget: int, hash_mb: int, timeout: float, use_cache: bool = False,
) -> Iterator[MoveAnalysis]:
    """Search contiguous game segments at full depth and publish in ply order.

    Search each position once, including the final position. The opponent's
    best reply supplies the played move's evaluation at the same full depth.
    Only best played moves need a separate search of the strongest alternative.
    """
    moves = [chess.Move.from_uci(move.uci_move) for move in parsed_game.moves]
    if not moves:
        return
    engine_path = stockfish_executable(engine_path)
    key = analysis_cache_key(parsed_game, engine_path, depth, pv_length) if use_cache else None
    if key:
        with _cache_lock:
            cached = _analysis_cache.get(key)
            if cached is not None:
                _analysis_cache.move_to_end(key)
        if cached is not None:
            for result in json.loads(cached):
                yield MoveAnalysis(**result)
            return
    position_count = len(moves) + 1
    book_moves = opening_move_flags(chess.Board(parsed_game.starting_fen), moves)
    workers = min(max(1, cpu_budget), position_count, 8)
    # Small blocks prevent a difficult opening/middlegame segment from holding
    # up otherwise idle engines. Adjacent positions still share the hash table.
    chunk_size = position_count if workers == 1 else min(4, (position_count + workers - 1) // workers)
    updates: Queue = Queue()
    stopped = Event()
    blocks: Queue[int] = Queue()

    def search_worker() -> None:
        engine = None
        try:
            engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=timeout)
            options = {}
            if "Threads" in engine.options:
                options["Threads"] = max(1, cpu_budget // workers)
            if "Hash" in engine.options:
                options["Hash"] = max(1, hash_mb // workers)
            if options:
                engine.configure(options)
            while not stopped.is_set():
                try:
                    start = blocks.get_nowait()
                except Empty:
                    break
                board = chess.Board(parsed_game.starting_fen)
                for move in moves[:start]:
                    board.push(move)
                for index in range(start, min(start + chunk_size, position_count)):
                    if stopped.is_set():
                        break
                    played = moves[index] if index < len(moves) else None
                    book = book_moves[index] if played is not None else False
                    lines = _search_position(engine, board, played, depth, book=book)
                    updates.put((index, lines, None))
                    if played is not None:
                        board.push(played)
        except Exception as error:
            updates.put((None, None, error))
        finally:
            if engine is not None:
                try:
                    engine.quit()
                except (chess.engine.EngineError, OSError, TimeoutError):
                    pass

    pending: dict[int, list[chess.engine.InfoDict]] = {}
    completed = []
    board = chess.Board(parsed_game.starting_fen)
    next_index = 0
    previous_opportunity: float | None = None
    with ThreadPoolExecutor(max_workers=workers) as executor:
        starts = list(range(0, position_count, chunk_size))
        # Start from both ends: a slow final segment should not begin only after
        # all earlier work has finished. The first block still publishes promptly.
        front, back = 0, len(starts) - 1
        scheduled = []
        while front <= back:
            scheduled.append(starts[front])
            if front != back:
                scheduled.append(starts[back])
            front += 1
            back -= 1
        for start in scheduled:
            blocks.put(start)
        for _ in range(workers):
            executor.submit(search_worker)
        try:
            while next_index < len(moves):
                index, result, error = updates.get()
                if error is not None:
                    raise error
                pending[index] = result
                while next_index in pending and next_index + 1 in pending:
                    before_lines = pending.pop(next_index)
                    played = pending[next_index + 1][0]
                    color = board.turn
                    result = _analyze_played_move(board, moves[next_index], before_lines,
                                                  played, previous_opportunity, pv_length,
                                                  book=book_moves[next_index])
                    points_before = expected_points(_score_for_color(before_lines[0]['score'], color))
                    previous_opportunity = 1 - points_before
                    next_index += 1
                    if key:
                        completed.append(asdict(result))
                    yield result
        finally:
            stopped.set()
    if key:
        with _cache_lock:
            _analysis_cache[key] = json.dumps(completed)
            _analysis_cache.move_to_end(key)
            while len(_analysis_cache) > 16:
                _analysis_cache.popitem(last=False)


def _search_position(engine: chess.engine.SimpleEngine, board: chess.Board,
                     played: chess.Move | None, depth: int, *,
                     book: bool = False) -> list[chess.engine.InfoDict]:
    limit = chess.engine.Limit(depth=depth)
    info = chess.engine.INFO_SCORE | chess.engine.INFO_PV
    best = engine.analyse(board, limit, info=info)
    lines = [best]
    if (played is not None and (best.get('pv') or [None])[0] == played
            and not book):
        alternatives = [move for move in board.legal_moves if move != played]
        if alternatives:
            lines.append(engine.analyse(board, limit, root_moves=alternatives, info=info))
    return lines


@lru_cache(maxsize=1)
def opening_book() -> dict[str, list[str]]:
    return json.loads((Path(__file__).parent / "data" / "openings.json").read_text())


@lru_cache(maxsize=1)
def opening_positions() -> frozenset[str]:
    """Include terminal positions, which have no outgoing entry in the file."""
    positions = set(opening_book())
    for epd, moves in opening_book().items():
        board = chess.Board(epd)
        for uci in moves:
            board.push_uci(uci)
            positions.add(board.epd())
            board.pop()
    return frozenset(positions)


def is_book_move(board: chess.Board, move: chess.Move) -> bool:
    if board.ply() >= 40 or move not in board.legal_moves:
        return False
    if move.uci() in opening_book().get(board.epd(), []):
        return True
    # A different move order can enter a known position through an edge absent
    # from the source line. EPD retains side, castling and legal en passant.
    after = board.copy(stack=False)
    after.push(move)
    return after.epd() in opening_positions()


def _matches_opening_order(board: chess.Board, moves: list[chess.Move], target: str) -> bool:
    """Verify a short transposition against an actual path in the theory file.

    Each side must play exactly the same moves, with the same resulting EPD.
    Merely returning to a known position after a detour is not sufficient.
    """
    remaining = {chess.WHITE: Counter(moves[::2]), chess.BLACK: Counter(moves[1::2])}
    if board.turn == chess.BLACK:
        remaining[chess.WHITE], remaining[chess.BLACK] = remaining[chess.BLACK], remaining[chess.WHITE]
    failed = set()

    def visit(left: int) -> bool:
        if not left:
            return board.epd() == target
        state = (board.epd(), tuple(tuple(sorted((m.uci(), n) for m, n in remaining[color].items() if n))
                                   for color in (chess.WHITE, chess.BLACK)))
        if state in failed:
            return False
        choices = remaining[board.turn]
        for uci in opening_book().get(board.epd(), []):
            move = chess.Move.from_uci(uci)
            if not choices[move] or move not in board.legal_moves:
                continue
            choices[move] -= 1
            board.push(move)
            found = visit(left - 1)
            board.pop()
            choices[move] += 1
            if found:
                return True
        failed.add(state)
        return False

    return visit(len(moves))


def opening_move_flags(board: chess.Board, moves: list[chess.Move]) -> list[bool]:
    """Determine one continuous theory prefix before starting any engines."""
    flags = [False] * len(moves)
    positions = [board.copy(stack=False)]
    for move in moves:
        if positions[-1].ply() >= 40:
            break
        after = positions[-1].copy(stack=False)
        after.push(move)
        positions.append(after)
    index = 0
    limit = len(positions) - 1
    while index < limit:
        if is_book_move(positions[index], moves[index]):
            flags[index] = True
            index += 1
            continue
        # A reordered sequence may cross positions absent from the file before
        # joining its canonical line. Validate up to four moves per side, rather
        # than filling arbitrary gaps between unrelated known positions.
        matched_end = None
        for end in range(index + 2, min(limit, index + 8) + 1):
            target = positions[end].epd()
            if target not in opening_positions():
                continue
            for start in range(index, max(-1, end - 9), -1):
                if _matches_opening_order(positions[start].copy(stack=False), moves[start:end], target):
                    matched_end = end
                    break
            if matched_end is not None:
                break
        if matched_end is None:
            break
        flags[index:matched_end] = [True] * (matched_end - index)
        index = matched_end
    return flags


def analyze_moves(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    played_moves: Iterable[chess.Move],
    depth: int,
    pv_length: int,
) -> Iterator[MoveAnalysis]:
    limit = chess.engine.Limit(depth=depth)
    info = chess.engine.INFO_SCORE | chess.engine.INFO_PV
    previous_opportunity: float | None = None
    played_moves = list(played_moves)
    book_moves = opening_move_flags(board, played_moves)

    for played_move, book in zip(played_moves, book_moves, strict=True):
        before_lines = engine.analyse(board, limit, multipv=3, info=info)
        played = next((line for line in before_lines
                       if (line.get("pv") or [None])[0] == played_move), None)
        if played is None:
            played = engine.analyse(board, limit, root_moves=[played_move], info=info)
        points_before = expected_points(_score_for_color(before_lines[0]['score'], board.turn))
        yield _analyze_played_move(board, played_move, before_lines, played, previous_opportunity, pv_length,
                                  book=book)
        previous_opportunity = 1 - points_before


def _analyze_played_move(board: chess.Board, played_move: chess.Move,
                         before_lines: list[chess.engine.InfoDict], played: chess.engine.InfoDict,
                         previous_opportunity: float | None, pv_length: int, *, book: bool) -> MoveAnalysis:
    color = board.turn
    before = board.copy()
    best = before_lines[0]
    before_cp = _score_for_color(best["score"], color)
    played_cp = _score_for_color(played["score"], color)
    points_before = expected_points(before_cp)
    points_after = expected_points(played_cp)
    loss = max(0.0, points_before - points_after)
    best_move = (best.get("pv") or [played_move])[0]
    is_best = played_move == best_move
    classification = classify_loss(loss, is_best=is_best)
    alternative = (expected_points(_score_for_color(before_lines[1]["score"], color))
                   if len(before_lines) > 1 else None)
    other_choice = alternative if is_best else points_before
    board.push(played_move)

    if book:
        classification = "book"
    elif (loss < 0.02 and is_playable_position(played_cp) and other_choice is not None
          and other_choice < 0.85 and not board.is_game_over()
          and offers_new_sacrifice(before, board, played_move)):
        classification = "brilliant"
    elif is_great_move(played_cp, points_before, alternative, is_best=is_best):
        classification = "great"
    elif (previous_opportunity is not None and previous_opportunity < 0.75
          and points_before >= 0.75 and points_after < 0.65
          and loss >= 0.10):
        classification = "miss"

    return MoveAnalysis(
        evaluation_before=_score_for_color(best["score"], chess.WHITE),
        evaluation_after=_score_for_color(played["score"], chess.WHITE),
        centipawn_loss=max(0, before_cp - played_cp),
        classification=classification,
        best_move=best_move.uci(),
        principal_variation=[move.uci() for move in best.get("pv", [])[:pv_length]],
        candidate_moves=[line["pv"][0].uci() for line in before_lines if line.get("pv")],
    )


def _capture_gain(board: chess.Board, move: chess.Move) -> int:
    victim = board.piece_type_at(move.to_square)
    gain = 100 if board.is_en_passant(move) else PIECE_VALUES.get(victim, 0)
    if move.promotion:
        gain += PIECE_VALUES[move.promotion] - PIECE_VALUES[chess.PAWN]
    board.push(move)
    try:
        reply = max((_capture_gain(board, capture) for capture in list(board.legal_moves)
                     if capture.to_square == move.to_square and board.is_capture(capture)),
                    default=0)
        return gain - max(0, reply)
    finally:
        board.pop()


def _hanging_pieces(board: chess.Board, color: chess.Color) -> dict[int, int]:
    probe = board.copy(stack=False)
    if probe.turn == color:
        try:
            probe.push(chess.Move.null())
        except ValueError:
            return {}
    hanging: dict[int, int] = {}
    for capture in list(probe.legal_moves):
        victim = probe.piece_at(capture.to_square)
        if (victim is not None and victim.color == color
                and victim.piece_type not in (chess.PAWN, chess.KING)
                and probe.is_capture(capture)):
            gain = _capture_gain(probe, capture)
            if gain >= 200:
                hanging[capture.to_square] = max(gain, hanging.get(capture.to_square, 0))
    return hanging


def offers_new_sacrifice(before: chess.Board, after: chess.Board, move: chess.Move) -> bool:
    old = _hanging_pieces(before, before.turn)
    captured = (100 if before.is_en_passant(move)
                else PIECE_VALUES.get(before.piece_type_at(move.to_square), 0))
    promotion_gain = PIECE_VALUES.get(move.promotion, 100) - 100
    for square, gain in _hanging_pieces(after, before.turn).items():
        origin = move.from_square if square == move.to_square else square
        if gain - captured - promotion_gain >= 200 and gain > old.get(origin, 0):
            return True
    return False


def _score_for_color(score: chess.engine.PovScore, color: chess.Color) -> int:
    value = score.pov(color).score(mate_score=100_000)
    if value is None:
        raise ValueError("Stockfish returned an empty score")
    return value

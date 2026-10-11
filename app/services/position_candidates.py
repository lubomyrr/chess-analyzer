"""Full-depth suggestions for the position currently being reviewed."""

from collections import OrderedDict
from contextlib import suppress
import hashlib
from pathlib import Path
import shutil
from threading import Lock

import chess
import chess.engine

from app.services.chess_analysis import _file_digest
from app.services.move_quality import classify_loss, expected_points
from app.services.stockfish_runtime import stockfish_executable

_cache: OrderedDict[str, tuple[str, ...]] = OrderedDict()
_cache_lock = Lock()
_search_lock = Lock()
_engine: chess.engine.SimpleEngine | None = None
_engine_config: tuple | None = None


def _select_viable_candidates(board: chess.Board, lines: list[chess.engine.InfoDict]) -> tuple[str, ...]:
    """Keep the best root and alternatives through Inaccuracy; hide errors."""
    roots = [line for line in lines if line.get('pv') and line['pv'][0] in board.legal_moves]
    if not roots:
        return ()
    best = roots[0]
    moves = [best['pv'][0].uci()]
    if 'score' not in best:
        return tuple(moves)
    best_score = best['score'].pov(board.turn)
    best_points = expected_points(best_score.score(mate_score=100_000))
    for line in roots[1:]:
        move = line['pv'][0].uci()
        if move in moves or 'score' not in line:
            continue
        score = line['score'].pov(board.turn)
        loss = best_points - expected_points(score.score(mate_score=100_000))
        if classify_loss(loss) not in {'mistake', 'blunder'}:
            moves.append(move)
    return tuple(moves[:3])


def _candidate_key(board: chess.Board, engine_path: str, depth: int) -> str:
    path = Path(shutil.which(engine_path) or engine_path)
    stat = path.stat()
    fingerprint = _file_digest(str(path), stat.st_size, stat.st_mtime_ns)
    history = ' '.join(move.uci() for move in board.move_stack)
    return hashlib.sha256(f'{fingerprint}|{depth}|{board.root().fen()}|{history}'.encode()).hexdigest()


def position_candidates(board: chess.Board, *, engine_path: str, depth: int,
                        hash_mb: int, timeout: float) -> list[str] | None:
    """None means the suggestion engine is busy; callers can retry without queuing work."""
    global _engine, _engine_config
    if board.is_game_over():
        return []
    engine_path = stockfish_executable(engine_path)
    key = _candidate_key(board, engine_path, depth)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return list(cached)
    if not _search_lock.acquire(blocking=False):
        return None
    try:
        stat = Path(engine_path).stat()
        config = (engine_path, min(hash_mb, 128), timeout, stat.st_size, stat.st_mtime_ns)
        if _engine is None or config != _engine_config:
            if _engine is not None:
                with suppress(chess.engine.EngineError, OSError, TimeoutError):
                    _engine.quit()
            _engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=timeout)
            options = {name: value for name, value in [('Threads', 1), ('Hash', config[1])]
                       if name in _engine.options}
            if options:
                _engine.configure(options)
            _engine_config = config
        lines = _engine.analyse(board, chess.engine.Limit(depth=depth), multipv=3,
                                info=chess.engine.INFO_SCORE | chess.engine.INFO_PV)
        moves = _select_viable_candidates(board, lines)
        with _cache_lock:
            _cache[key] = moves
            _cache.move_to_end(key)
            while len(_cache) > 512:
                _cache.popitem(last=False)
        return list(moves)
    except (chess.engine.EngineError, OSError, TimeoutError):
        if _engine is not None:
            _engine.close()
        _engine = None
        _engine_config = None
        raise
    finally:
        _search_lock.release()


def close_candidate_engine() -> None:
    global _engine, _engine_config
    with _search_lock:
        if _engine is not None:
            with suppress(chess.engine.EngineError, OSError, TimeoutError):
                _engine.quit()
        _engine = None
        _engine_config = None

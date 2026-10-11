import chess
import chess.engine
import pytest

from app.services import position_candidates as service


@pytest.fixture
def candidates(monkeypatch, tmp_path):
    service.close_candidate_engine()
    service._cache.clear()
    engine_path = tmp_path / 'engine'
    engine_path.write_bytes(b'test engine')
    engines = []

    class Engine:
        options = {'Threads': None, 'Hash': None}
        calls = []
        closed = False

        def configure(self, options):
            self.configured = options

        def analyse(self, board, limit, **kwargs):
            self.calls.append((board.copy(), limit.depth, kwargs))
            return [{'pv': [chess.Move.from_uci(move)]} for move in ['e2e4', 'd2d4', 'g1f3']]

        def quit(self):
            self.closed = True

        def close(self):
            self.closed = True

    def create(*args, **kwargs):
        engine = Engine()
        engine.calls = []
        engines.append(engine)
        return engine

    monkeypatch.setattr(chess.engine.SimpleEngine, 'popen_uci', create)
    yield dict(engine_path=str(engine_path), depth=20, hash_mb=512, timeout=120), engines
    service.close_candidate_engine()
    service._cache.clear()


def test_suggestions_keep_depth_three_lines_and_reuse_cached_results(candidates):
    options, engines = candidates
    first = service.position_candidates(chess.Board(), **options)
    first.clear()
    assert service.position_candidates(chess.Board(), **options) == ['e2e4', 'd2d4', 'g1f3']
    assert len(engines) == 1
    assert len(engines[0].calls) == 1
    _, depth, kwargs = engines[0].calls[0]
    assert depth == 20 and kwargs['multipv'] == 3
    assert engines[0].configured == {'Threads': 1, 'Hash': 128}
    service.position_candidates(chess.Board(), **{**options, 'depth': 21})
    assert len(engines[0].calls) == 2


def test_busy_engine_does_not_queue_another_search(candidates):
    options, engines = candidates
    service._search_lock.acquire()
    try:
        assert service.position_candidates(chess.Board(), **options) is None
    finally:
        service._search_lock.release()
    assert engines == []


def test_identical_fens_with_different_repetition_histories_have_distinct_keys(candidates):
    options, _ = candidates
    boards = [chess.Board(), chess.Board()]
    for board, moves in zip(boards, [['g1f3', 'g8f6', 'f3g1', 'f6g8'],
                                   ['b1c3', 'b8c6', 'c3b1', 'c6b8']]):
        for move in moves:
            board.push_uci(move)
    assert boards[0].fen() == boards[1].fen()
    assert service._candidate_key(boards[0], options['engine_path'], 20) != service._candidate_key(
        boards[1], options['engine_path'], 20)


def test_engine_failure_closes_process_and_next_request_can_retry(candidates, monkeypatch):
    options, engines = candidates
    service.position_candidates(chess.Board(), **options)
    old = engines[0]

    def fail(*args, **kwargs):
        raise chess.engine.EngineError('Stopped')

    monkeypatch.setattr(old, 'analyse', fail)
    board = chess.Board()
    board.push_uci('e2e4')
    with pytest.raises(chess.engine.EngineError, match='Stopped'):
        service.position_candidates(board, **options)
    assert old.closed
    assert service.position_candidates(board, **options)
    assert len(engines) == 2

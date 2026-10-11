import chess
import chess.engine
import pytest

from app.services import position_candidates as service


def candidate(move, score, color=chess.WHITE):
    return {'pv': [chess.Move.from_uci(move)], 'score': chess.engine.PovScore(score, color)}


@pytest.mark.parametrize(('scores', 'expected'), [
    ([30, 20, 10], ['e2e4', 'd2d4', 'g1f3']),
    ([30, 0, -200], ['e2e4', 'd2d4']),
    ([0, -75, -100], ['e2e4', 'd2d4', 'g1f3']),
    ([0, -75, -150], ['e2e4', 'd2d4']),
    ([0, -150, -400], ['e2e4']),
    ([400, 0, -400], ['e2e4']),
    ([-400, -420, -900], ['e2e4', 'd2d4']),
])
def test_only_non_error_alternatives_are_shown(scores, expected):
    lines = [candidate(move, chess.engine.Cp(score))
             for move, score in zip(['e2e4', 'd2d4', 'g1f3'], scores)]
    assert list(service._select_viable_candidates(chess.Board(), lines)) == expected


def test_candidates_are_compared_from_black_perspective():
    board = chess.Board()
    board.push_san('e4')
    lines = [candidate('e7e5', chess.engine.Cp(-30)),
             candidate('c7c5', chess.engine.Cp(-20)),
             candidate('f7f6', chess.engine.Cp(300))]
    assert service._select_viable_candidates(board, lines) == ('e7e5', 'c7c5')


@pytest.mark.parametrize(('best', 'alternative', 'expected'), [
    (chess.engine.Cp(0), chess.engine.Mate(-1), ('e2e4',)),
    (chess.engine.Mate(3), chess.engine.Mate(-2), ('e2e4',)),
    (chess.engine.Cp(-1000), chess.engine.Mate(-1), ('e2e4', 'd2d4')),
    (chess.engine.Mate(-8), chess.engine.Mate(-1), ('e2e4', 'd2d4')),
])
def test_mate_alternatives_follow_the_same_error_classification(best, alternative, expected):
    lines = [candidate('e2e4', best), candidate('d2d4', alternative)]
    assert service._select_viable_candidates(chess.Board(), lines) == expected


def test_single_legal_reply_has_one_arrow():
    board = chess.Board('7k/8/5K2/6Q1/8/8/8/8 b - - 0 1')
    assert list(board.legal_moves) == [chess.Move.from_uci('h8h7')]
    assert service._select_viable_candidates(board, [candidate('h8h7', chess.engine.Mate(-2))]) == ('h8h7',)


def test_unscored_duplicate_and_illegal_alternatives_are_not_guessed():
    lines = [candidate('e2e4', chess.engine.Cp(30)), candidate('e2e4', chess.engine.Cp(30)),
             {'pv': [chess.Move.from_uci('d2d4')]}, candidate('e7e5', chess.engine.Cp(30))]
    assert service._select_viable_candidates(chess.Board(), lines) == ('e2e4',)


def test_endpoint_does_not_return_old_unfiltered_three_move_storage(monkeypatch):
    from types import SimpleNamespace
    from fastapi import Response
    from app.api.routes import games

    monkeypatch.setattr(games, 'get_game', lambda *args: SimpleNamespace(raw_pgn='[Result "*"]\n\n1. e4 *'))
    monkeypatch.setattr(games, 'get_game_moves', lambda *args: [SimpleNamespace(
        ply=1, candidate_moves=['e2e4', 'd2d4', 'g1f3'])])
    monkeypatch.setattr(games, 'position_candidates', lambda *args, **kwargs: ['e2e4'])
    result = games.read_position_candidates(1, 0, Response(), object())
    assert result.ready
    assert result.candidate_moves == ['e2e4']


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
            moves = ['e2e4', 'd2d4', 'g1f3'] if board.turn else ['e7e5', 'c7c5', 'g8f6']
            return [{'pv': [chess.Move.from_uci(move)],
                     'score': chess.engine.PovScore(chess.engine.Cp(score), board.turn)}
                    for move, score in zip(moves, [30, 20, 10])]

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

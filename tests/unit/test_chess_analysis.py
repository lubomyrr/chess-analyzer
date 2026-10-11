import chess
import chess.engine
import pytest
from threading import Barrier

from app.services.chess_analysis import analyze_moves, is_book_move, offers_new_sacrifice
from app.services.move_quality import classify_loss, expected_points, is_great_move
from app.services import chess_analysis
from app.services.pgn_parser import parse_pgn


class StubEngine:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def analyse(self, board, limit, **kwargs):
        self.calls.append((board.fen(), limit.depth, kwargs))
        return self.results.pop(0)


def line(score, pv):
    return {"score": chess.engine.PovScore(chess.engine.Cp(score), chess.WHITE),
            "pv": [chess.Move.from_uci(move) for move in pv.split()]}


@pytest.mark.parametrize(('loss', 'expected'), [
    (0, 'excellent'), (.0199, 'excellent'), (.02, 'good'),
    (.0499, 'good'), (.05, 'inaccuracy'), (.0999, 'inaccuracy'),
    (.10, 'mistake'), (.1999, 'mistake'), (.20, 'blunder'), (1, 'blunder'),
])
def test_expected_points_boundaries(loss, expected):
    assert classify_loss(loss) == expected
    assert classify_loss(0, is_best=True) == 'best'


def test_expected_points_symmetric_and_position_sensitive():
    assert expected_points(0) == .5
    assert expected_points(100) == pytest.approx(1 - expected_points(-100))
    assert expected_points(1000) - expected_points(900) < expected_points(100) - expected_points(0)
    assert expected_points(100000) == pytest.approx(1)
    assert expected_points(-100000) == pytest.approx(0)


@pytest.mark.parametrize(('played_score','expected'), [
    (40,'excellent'), (10,'good'), (-40,'inaccuracy'), (-130,'mistake'), (-300,'blunder'),
])
def test_non_best_moves_are_never_best(monkeypatch, played_score, expected):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine = StubEngine([[line(50,'e2e4'),line(played_score,'d2d4')], [line(0,'e7e5')]])
    result = next(analyze_moves(engine,chess.Board(),[chess.Move.from_uci('d2d4')],16,4))
    assert result.classification == expected
    assert result.best_move == 'e2e4'
    assert result.centipawn_loss == 50-played_score


def test_black_score_and_restricted_root_search(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    board = chess.Board(); board.push_uci('e2e4')
    engine = StubEngine([[line(-30,'e7e5'),line(0,'c7c5')],line(130,'a7a6'),[line(130,'g1f3')]])
    result = next(analyze_moves(engine,board,[chess.Move.from_uci('a7a6')],16,4))
    assert result.evaluation_before == -30
    assert result.evaluation_after == 130
    assert result.centipawn_loss == 160
    assert result.classification == 'mistake'
    assert engine.calls[1][2]['root_moves'] == [chess.Move.from_uci('a7a6')]
    assert all(call[1] == 16 for call in engine.calls)


def test_each_position_is_searched_once_without_unused_final_search():
    engine = StubEngine([[line(20,'e2e4'),line(10,'d2d4')],
                         [line(15,'e7e5'),line(25,'c7c5')], [line(25,'g1f3')]])
    results = list(analyze_moves(engine,chess.Board(),map(chess.Move.from_uci,['e2e4','e7e5']),16,4))
    assert len(results) == 2
    assert len(engine.calls) == 2
    assert all(call[2] == {'multipv': 3, 'info': chess.engine.INFO_SCORE | chess.engine.INFO_PV}
               for call in engine.calls)
    assert all(result.classification == 'book' for result in results)


def test_book_matches_positions_and_castling_rights():
    board=chess.Board()
    assert is_book_move(board,chess.Move.from_uci('e2e4'))
    board.remove_piece_at(chess.D1)
    assert not is_book_move(board,chess.Move.from_uci('e2e4'))


def test_book_recognizes_sicilian_transposition_and_a_continuous_prefix():
    parsed = parse_pgn('[Result "*"]\n\n1. Nf3 c5 2. e4 e6 3. Nc3 a6 '
                       '4. d4 cxd4 5. Nxd4 b5 6. Bd3 Bb7 7. O-O h5 *')
    board = chess.Board()
    moves = [chess.Move.from_uci(move.uci_move) for move in parsed.moves]
    board.push(moves[0])
    board.push(moves[1])
    assert moves[2].uci() not in chess_analysis.opening_book().get(board.epd(), [])
    assert is_book_move(board, moves[2])  # 2.e4 reaches known theory in another order.
    start = chess.Board()
    flags = chess_analysis.opening_move_flags(start, moves)
    assert flags == [True] * 13 + [False]
    assert start.fen() == chess.STARTING_FEN
    assert not start.move_stack


def test_book_does_not_resume_after_a_detour_back_to_the_initial_position():
    parsed = parse_pgn('[Result "*"]\n\n1. Nf3 Nf6 2. Ng1 Ng8 3. e4 *')
    moves = [chess.Move.from_uci(move.uci_move) for move in parsed.moves]
    board = chess.Board()
    for move in moves[:-1]:
        board.push(move)
    assert is_book_move(board, moves[-1])
    # Neither a known future endpoint nor a known later move may fill this gap.
    assert chess_analysis.opening_move_flags(chess.Board(), moves) == [True, True, False, False, False]


def test_book_includes_terminal_positions_and_preserves_castling_rights(monkeypatch, request):
    board = chess.Board()
    board.push_san('e4')
    board.push_san('c5')
    terminal_move = board.parse_san('Nf3')
    source = {board.epd(): [terminal_move.uci()]}
    monkeypatch.setattr(chess_analysis, 'opening_book', lambda: source)
    chess_analysis.opening_positions.cache_clear()
    request.addfinalizer(chess_analysis.opening_positions.cache_clear)
    transposed = chess.Board()
    transposed.push_san('Nf3')
    transposed.push_san('c5')
    assert is_book_move(transposed, transposed.parse_san('e4'))
    transposed.castling_rights = 0
    assert not is_book_move(transposed, transposed.parse_san('e4'))


def test_book_does_not_mark_a_late_custom_position_as_an_opening():
    board = chess.Board()
    board.fullmove_number = 21
    move = board.parse_san('e4')
    assert not is_book_move(board, move)
    assert chess_analysis.opening_move_flags(board, [move]) == [False]


def test_theory_overrides_engine_classification_without_replacing_scores():
    engine = StubEngine([[line(100, 'd2d4'), line(10, 'e2e4')]])
    result = next(analyze_moves(engine, chess.Board(), [chess.Move.from_uci('e2e4')], 20, 4))
    assert result.classification == 'book'
    assert result.best_move == 'd2d4'
    assert result.evaluation_before == 100
    assert result.evaluation_after == 10
    assert result.centipawn_loss == 90


def test_parallel_engines_use_the_precomputed_theory_prefix(monkeypatch):
    parsed = parse_pgn('[Result "*"]\n\n1. Nf3 c5 2. e4 e6 3. Nc3 a6 '
                       '4. d4 cxd4 5. Nxd4 b5 6. Bd3 Bb7 7. O-O h5 *')
    calls = []

    class Engine:
        options = {}

        def quit(self):
            pass

        def analyse(self, board, limit, **kwargs):
            calls.append((board.ply(), limit.depth, kwargs))
            if 'root_moves' in kwargs:
                return line(0, kwargs['root_moves'][0].uci())
            uci = (parsed.moves[board.ply()].uci_move if board.ply() < len(parsed.moves)
                   else next(iter(board.legal_moves)).uci())
            return line(0, uci)

    monkeypatch.setattr(chess.engine.SimpleEngine, 'popen_uci', lambda *args, **kwargs: Engine())
    results = list(chess_analysis.analyze_game_parallel(
        parsed, engine_path='test', depth=20, pv_length=4, cpu_budget=3, hash_mb=96, timeout=120))
    assert [result.classification for result in results] == ['book'] * 13 + ['best']
    assert [ply for ply, _, kwargs in calls if 'root_moves' in kwargs] == [13]
    assert sorted(ply for ply, _, kwargs in calls if 'root_moves' not in kwargs) == list(range(15))
    assert all(depth == 20 for _, depth, _ in calls)
    assert all(result.evaluation_before == result.evaluation_after == 0 for result in results)


def test_only_move_is_best_not_automatically_great(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine=StubEngine([[line(20,'e2e4')],[line(10,'e7e5')]])
    result=next(analyze_moves(engine,chess.Board(),[chess.Move.from_uci('e2e4')],16,4))
    assert result.classification == 'best'
    assert result.centipawn_loss == 0


def test_great_requires_meaningful_alternative_gap(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine=StubEngine([[line(300,'e2e4'),line(0,'d2d4')],[line(300,'e7e5')]])
    assert next(analyze_moves(engine,chess.Board(),[chess.Move.from_uci('e2e4')],16,4)).classification == 'great'


SACRIFICE_FEN='rnbq1rk1/pppn1ppp/4p3/3pP3/1b1P4/2NB1N2/PPP2PPP/R1BQK2R w KQ - 3 7'


@pytest.mark.parametrize(('fen','uci','expected'), [
    (SACRIFICE_FEN,'d3h7',True),
    ('4k3/8/2p5/3r4/8/8/8/3RK3 w - - 0 20','d1d5',False),
    ('4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 20','e4d5',False),
    ('4k3/8/8/3p4/4R3/8/8/4K3 w - - 0 20','e1f1',False),
])
def test_sacrifices_exclude_trades_pawns_and_existing_hanging_pieces(fen,uci,expected):
    before=chess.Board(fen); after=before.copy(); move=chess.Move.from_uci(uci)
    assert move in before.legal_moves
    after.push(move)
    assert offers_new_sacrifice(before,after,move) is expected
    assert before.fen() == fen


@pytest.mark.parametrize(('score','alternative','expected'), [
    (30,0,'brilliant'), (-30,-50,'brilliant'), (-100,-110,'best'), (900,850,'best'),
])
def test_brilliant_requires_sound_sacrifice_and_not_already_winning(monkeypatch,score,alternative,expected):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine=StubEngine([[line(score,'d3h7'),line(alternative,'e1g1')],[line(score,'g8h7')]])
    result=next(analyze_moves(engine,chess.Board(SACRIFICE_FEN),[chess.Move.from_uci('d3h7')],16,4))
    assert result.classification == expected


def test_miss_follows_opponent_error(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine=StubEngine([[line(0,'e2e4'),line(-400,'a2a3')],
                         [line(-400,'e7e5'),line(0,'a7a6')], [line(0,'e2e4')]])
    results=list(analyze_moves(engine,chess.Board(),map(chess.Move.from_uci,['a2a3','a7a6']),16,4))
    assert [result.classification for result in results] == ['blunder','miss']


def test_losing_existing_win_is_not_miss(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    engine=StubEngine([[line(400,'e2e4'),line(0,'a2a3')], [line(0,'e7e5')]])
    assert next(analyze_moves(engine,chess.Board(),[chess.Move.from_uci('a2a3')],16,4)).classification == 'blunder'


def test_checkmate_terminal_score(monkeypatch):
    monkeypatch.setattr('app.services.chess_analysis.is_book_move', lambda *args: False)
    board=chess.Board('7k/5Q2/6K1/8/8/8/8/8 w - - 0 1')
    winning={'score':chess.engine.PovScore(chess.engine.Mate(1),chess.WHITE),'pv':[chess.Move.from_uci('f7g7')]}
    terminal={'score':chess.engine.PovScore(chess.engine.Mate(0),chess.BLACK)}
    engine=StubEngine([[winning],[terminal]])
    result=next(analyze_moves(engine,board,[chess.Move.from_uci('f7g7')],16,4))
    assert board.is_checkmate()
    assert result.evaluation_after == 99999
    assert result.classification == 'best'
    assert len(engine.calls) == 1


QUEEN_SACRIFICE_FEN = 'r1b2kr1/p4ppp/2qB4/2p5/2Q1N1n1/3P2P1/PP5P/R4K1R b - - 2 21'


def test_black_queen_sacrifice_in_equal_position_is_brilliant():
    engine = StubEngine([
        [line(37, 'c6d6 e4d6 g4e3 f1f2 e3c4'), line(132, 'f8e8')],
        [line(27, 'e4d6'), line(-438, 'a1e1')],
    ])
    result = next(analyze_moves(engine, chess.Board(QUEEN_SACRIFICE_FEN),
                               [chess.Move.from_uci('c6d6')], 20, 5))
    assert result.classification == 'brilliant'
    assert result.centipawn_loss == 0


def test_taking_sacrificed_queen_is_great_not_brilliant():
    board = chess.Board(QUEEN_SACRIFICE_FEN)
    board.push_uci('c6d6')
    engine = StubEngine([
        [line(27, 'e4d6 g4e3 f1e2 e3c4'), line(-438, 'a1e1')],
        [line(27, 'g4e3')],
    ])
    result = next(analyze_moves(engine, board, [chess.Move.from_uci('e4d6')], 20, 4))
    assert result.classification == 'great'


@pytest.mark.parametrize(('best_cp', 'alternative_cp', 'is_best', 'expected'), [
    (-30, -220, True, True),
    (-100, -400, True, False),
    (30, 20, True, False),
    (75, 0, True, False),
    (220, 110, True, True),
    (350, 250, True, False),
    (30, -220, False, False),
    (900, 850, True, False),
])
def test_great_defensive_moves_and_false_positives(best_cp, alternative_cp, is_best, expected):
    assert is_great_move(best_cp, expected_points(best_cp), expected_points(alternative_cp),
                         is_best=is_best) is expected


@pytest.mark.parametrize("fail", [False, True])
def test_parallel_search_preserves_history_order_and_miss_across_segments(monkeypatch, fail):
    parsed = parse_pgn('[Result "*"]\n\n1. a3 a6 2. h3 h6 *')
    engines = []
    positions = []
    started = Barrier(2)

    class Engine:
        options = {"Threads": None, "Hash": None}
        closed = False

        def configure(self, options):
            self.configured = options

        def quit(self):
            self.closed = True

        def analyse(self, board, limit, **kwargs):
            ply = board.ply()
            positions.append((ply, len(board.move_stack), limit.depth))
            if ply in (0, 3):
                started.wait(timeout=5)
            if fail and ply == 2:
                raise RuntimeError('Search failed')
            assert 'multipv' not in kwargs
            assert 'root_moves' not in kwargs
            played = chess.Move.from_uci(parsed.moves[ply].uci_move) if ply < 4 else None
            best = next(move for move in board.legal_moves if move != played)
            return line([0, 0, 400, 0, 0][ply], best.uci())

    def make_engine(*args, **kwargs):
        engine = Engine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", make_engine)
    analyses = chess_analysis.analyze_game_parallel(
        parsed, engine_path="test", depth=20, pv_length=4,
        cpu_budget=2, hash_mb=256, timeout=120,
    )
    if fail:
        with pytest.raises(RuntimeError, match="Search failed"):
            list(analyses)
    else:
        results = list(analyses)
        assert [result.evaluation_before for result in results] == [0, 0, 400, 0]
        assert [result.evaluation_after for result in results] == [0, 400, 0, 0]
        assert results[2].classification == "miss"
        assert sorted(positions) == [(ply, ply, 20) for ply in range(5)]
    assert all(ply == history and depth == 20 for ply, history, depth in positions)
    assert len(engines) == 2
    assert all(engine.closed for engine in engines)
    assert all(engine.configured == {"Threads": 1, "Hash": 128} for engine in engines)


def test_top_three_candidates_are_distinct_root_moves_not_pv_replies(monkeypatch):
    monkeypatch.setattr(chess_analysis, 'is_book_move', lambda *args: False)
    engine = StubEngine([[line(20, 'e2e4 e7e5'), line(10, 'd2d4 d7d5'), line(0, 'g1f3 g8f6')]])
    result = next(analyze_moves(engine, chess.Board(), [chess.Move.from_uci('e2e4')], 20, 4))
    assert result.candidate_moves == ['e2e4', 'd2d4', 'g1f3']
    assert result.principal_variation == ['e2e4', 'e7e5']


def test_fast_search_checks_alternatives_at_full_depth_only_for_best_moves(monkeypatch):
    monkeypatch.setattr(chess_analysis, 'is_book_move', lambda *args: False)
    parsed = parse_pgn('[Result "*"]\n\n1. a3 a6 *')
    calls = []

    class Engine:
        options = {}

        def quit(self):
            pass

        def analyse(self, board, limit, **kwargs):
            calls.append((board.ply(), limit.depth, kwargs))
            if 'root_moves' in kwargs:
                played = chess.Move.from_uci(parsed.moves[board.ply()].uci_move)
                assert played not in kwargs['root_moves']
                return line(-400 if board.turn else 400, kwargs['root_moves'][0].uci())
            move = parsed.moves[board.ply()].uci_move if board.ply() < 2 else next(iter(board.legal_moves)).uci()
            return line(0, move)

    monkeypatch.setattr(chess.engine.SimpleEngine, 'popen_uci', lambda *a, **kw: Engine())
    results = list(chess_analysis.analyze_game_parallel(parsed, engine_path='test', depth=20,
                   pv_length=4, cpu_budget=1, hash_mb=64, timeout=120))
    assert [result.classification for result in results] == ['great', 'great']
    assert len([call for call in calls if 'root_moves' not in call[2]]) == 3
    assert len([call for call in calls if 'root_moves' in call[2]]) == 2
    assert all(call[1] == 20 and 'multipv' not in call[2] for call in calls)


def test_completed_game_cache_does_not_rerun_engine_or_share_mutable_results(monkeypatch):
    parsed = parse_pgn('[Result "*"]\n\n1. a3 a6 *')
    monkeypatch.setattr(chess_analysis, 'analysis_cache_key', lambda *args: 'cache-test')
    with chess_analysis._cache_lock:
        chess_analysis._analysis_cache.pop('cache-test', None)
    starts = []

    class Engine:
        options = {}

        def quit(self):
            pass

        def analyse(self, board, limit, **kwargs):
            return line(0, next(iter(board.legal_moves)).uci())

    def make_engine(*a, **kw):
        starts.append(True)
        return Engine()

    monkeypatch.setattr(chess.engine.SimpleEngine, 'popen_uci', make_engine)
    kwargs = dict(engine_path='test', depth=20, pv_length=4, cpu_budget=1, hash_mb=64,
                  timeout=120, use_cache=True)
    first = list(chess_analysis.analyze_game_parallel(parsed, **kwargs))
    first[0].candidate_moves.clear()
    second = list(chess_analysis.analyze_game_parallel(parsed, **kwargs))
    assert len(starts) == 1
    assert len(second) == len(first) == 2
    assert second[0].candidate_moves

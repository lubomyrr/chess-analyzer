from pathlib import Path

import pytest

from app.services.pgn_parser import parse_pgn


FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "sample_blunder.pgn"
)


def test_parse_pgn_returns_headers_and_moves() -> None:
    raw_pgn = FIXTURE_PATH.read_text(encoding="utf-8")

    game = parse_pgn(raw_pgn)

    assert game.white_player == "Alice"
    assert game.black_player == "Bob"
    assert game.white_elo == 2017
    assert game.black_elo == 1999
    assert game.result == "1-0"
    assert len(game.moves) == 7
    assert game.moves[0].uci_move == "e2e4"
    assert game.moves[0].side == "white"
    assert game.moves[-1].san_move == "Qxf7#"


def test_parse_pgn_rejects_empty_file() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_pgn("")


def test_clock_times_track_each_player_separately() -> None:
    game = parse_pgn('[TimeControl "600"]\n\n1. e4 {[%clk 0:09:57.2]} e5 {[%clk 0:09:58.7]} '
                     '2. Nf3 {[%clk 0:09:55.9]} Nc6 {[%clk 0:09:57.5]} *')
    assert game.initial_clock_seconds == 600
    assert [move.clock_seconds for move in game.moves] == [597.2, 598.7, 595.9, 597.5]
    assert [move.thinking_time_seconds for move in game.moves] == [2.8, 1.3, 1.3, 1.2]


def test_increment_is_included_in_thinking_time() -> None:
    game = parse_pgn('[TimeControl "60+2"]\n\n1. e4 {[%clk 0:01:01.5]} e5 {[%clk 0:01:00]} '
                     '2. Nf3 {[%clk 0:00:59]} *')
    assert [move.thinking_time_seconds for move in game.moves] == [0.5, 2, 4.5]


def test_missing_clocks_do_not_merge_thinking_time() -> None:
    game = parse_pgn('[TimeControl "60"]\n\n1. e4 {[%clk 0:00:58]} e5 '
                     '2. Nf3 Nc6 {[%clk 0:00:50]} 3. Bc4 {[%clk 0:00:40]} *')
    assert [move.thinking_time_seconds for move in game.moves] == [2, None, None, None, None]


@pytest.mark.parametrize('control', ['?', '-', '40/7200:3600', '60d'])
def test_unsupported_controls_preserve_clock_but_do_not_guess_duration(control) -> None:
    game = parse_pgn(f'[TimeControl "{control}"]\n\n1. e4 {{[%clk 0:00:58]}} e5 {{[%emt 0:00:03.5]}} *')
    assert game.initial_clock_seconds is None
    assert game.moves[0].clock_seconds == 58
    assert game.moves[0].thinking_time_seconds is None
    assert game.moves[1].thinking_time_seconds == 3.5


def test_fen_game_does_not_guess_initial_time() -> None:
    game = parse_pgn('[SetUp "1"]\n[FEN "8/8/8/8/8/8/4k3/6K1 w - - 0 30"]\n'
                     '[TimeControl "600"]\n\n30. Kh1 {[%clk 0:00:58]} Kf3 {[%clk 0:00:40]} '
                     '31. Kg1 {[%clk 0:00:55]} *')
    assert game.initial_clock_seconds is None
    assert [move.thinking_time_seconds for move in game.moves] == [None, None, 3]


def test_clock_correction_does_not_create_negative_thinking_time() -> None:
    game = parse_pgn('[TimeControl "60"]\n\n1. e4 {[%clk 0:01:03]} *')
    assert game.moves[0].clock_seconds == 63
    assert game.moves[0].thinking_time_seconds is None

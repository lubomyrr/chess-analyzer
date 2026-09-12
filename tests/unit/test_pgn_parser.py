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

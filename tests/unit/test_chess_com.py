import pytest

from app.services import chess_com


def test_parse_chess_com_url_accepts_share_and_analysis_links() -> None:
    assert chess_com.parse_chess_com_url(
        "https://www.chess.com/game/live/118987818661"
    ) == ("live", "118987818661")
    assert chess_com.parse_chess_com_url(
        "https://www.chess.com/analysis/game/daily/832689402?tab=analysis"
    ) == ("daily", "832689402")


def test_parse_chess_com_url_rejects_another_host() -> None:
    with pytest.raises(ValueError, match="valid"):
        chess_com.parse_chess_com_url(
            "https://example.com/game/live/118987818661"
        )


def test_fetch_chess_com_pgn_finds_game_in_month(monkeypatch) -> None:
    pgn = '[White "Alice"]\n[Black "Bob"]\n\n1. e4 e5'

    def fake_get_json(url: str) -> dict:
        if "callback" in url:
            return {
                "game": {
                    "pgnHeaders": {"White": "Alice", "Date": "2026.09.02"}
                }
            }
        return {
            "games": [
                {
                    "url": "https://www.chess.com/game/live/12345",
                    "pgn": pgn,
                }
            ]
        }

    monkeypatch.setattr(chess_com, "_get_json", fake_get_json)

    assert chess_com.fetch_chess_com_pgn(
        "https://www.chess.com/game/live/12345"
    ) == pgn

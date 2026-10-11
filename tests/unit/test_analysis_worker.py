from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.game import Game
from app.models.game_move import GameMove
from app.services.chess_analysis import MoveAnalysis
from app.workers import analyze_game as worker


@pytest.mark.parametrize("fail", [False, True])
def test_worker_publishes_moves_before_completion(tmp_path, monkeypatch, fail):
    db_engine = create_engine(f"sqlite:///{tmp_path / 'analysis.sqlite'}")
    Base.metadata.create_all(db_engine)
    sessions = sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    raw_pgn = (Path(__file__).parents[1] / "fixtures/sample_blunder.pgn").read_text()
    with sessions() as db:
        game = Game(raw_pgn=raw_pgn, user_color="white", engine="stockfish",
                    white_player="White", black_player="Black", result="*", status="queued")
        db.add(game)
        db.commit()
        game_id = game.id

    def analyses(parsed_game, **kwargs):
        for index, move in enumerate(parsed_game.moves):
            if index == 1:
                with sessions() as reader:
                    assert reader.get(Game, game_id).status == "analyzing"
                    assert len(list(reader.scalars(select(GameMove)))) == 1
                if fail:
                    raise RuntimeError("Engine stopped")
            yield MoveAnalysis(20, 20, 0, "best", move.uci_move, [move.uci_move])

    monkeypatch.setattr(worker, "analyze_game_parallel", analyses)
    if fail:
        with pytest.raises(RuntimeError, match="Engine stopped"):
            worker.analyze_game_task.run(game_id)
    else:
        worker.analyze_game_task.run(game_id)
    with sessions() as reader:
        result = reader.get(Game, game_id)
        assert result.status == ("failed" if fail else "completed")
        if fail:
            assert result.error_message == "Engine stopped"
            assert len(list(reader.scalars(select(GameMove)))) == 1
        else:
            assert result.analyzed_at is not None
    db_engine.dispose()


def test_auto_threads_respect_available_cpus(monkeypatch):
    monkeypatch.setattr(worker.os, "sched_getaffinity", lambda _: {0, 1}, raising=False)
    assert worker.engine_thread_count(0) == 2
    assert worker.engine_thread_count(1) == 1
    monkeypatch.setattr(worker.os, "sched_getaffinity", lambda _: set(range(12)))
    assert worker.engine_thread_count(0) == 8

from app.services import stockfish_runtime as runtime


def test_avx2_selection_requires_supported_cpu_and_preserves_custom_paths(tmp_path, monkeypatch):
    engine = tmp_path / 'stockfish-avx2'
    engine.write_bytes(b'engine')
    cpu = tmp_path / 'cpuinfo'
    monkeypatch.setattr(runtime, 'OPTIMIZED_ENGINE', engine)
    monkeypatch.setattr(runtime, 'CPU_INFO', cpu)
    try:
        cpu.write_text('flags : sse2 avx2 bmi1 popcnt')
        runtime.stockfish_executable.cache_clear()
        assert runtime.stockfish_executable('/usr/games/stockfish') == str(engine)
        assert runtime.stockfish_executable('/custom/stockfish') == '/custom/stockfish'
        cpu.write_text('flags : sse2')
        runtime.stockfish_executable.cache_clear()
        assert runtime.stockfish_executable('/usr/games/stockfish') == '/usr/games/stockfish'
        cpu.unlink()
        runtime.stockfish_executable.cache_clear()
        assert runtime.stockfish_executable('/usr/games/stockfish') == '/usr/games/stockfish'
    finally:
        runtime.stockfish_executable.cache_clear()

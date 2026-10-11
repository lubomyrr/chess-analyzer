from functools import lru_cache
from pathlib import Path

OPTIMIZED_ENGINE = Path('/opt/stockfish/stockfish-avx2')
CPU_INFO = Path('/proc/cpuinfo')


@lru_cache(maxsize=8)
def stockfish_executable(configured_path: str) -> str:
    """Use the matching AVX2 build in Docker; preserve explicit custom engines."""
    if configured_path != '/usr/games/stockfish' or not OPTIMIZED_ENGINE.is_file():
        return configured_path
    try:
        cpu_info = CPU_INFO.read_text().split()
    except OSError:
        return configured_path
    if {'avx2', 'bmi1', 'popcnt'}.issubset(cpu_info):
        return str(OPTIMIZED_ENGINE)
    return configured_path

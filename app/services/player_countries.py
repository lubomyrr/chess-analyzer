from collections import OrderedDict
from functools import lru_cache
from io import StringIO
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from urllib.parse import quote, urlparse

import chess.pgn

from app.services.chess_com import _get_json

_cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
_profile_lock = Lock()


@lru_cache(maxsize=1)
def supported_countries() -> frozenset[str]:
    assets = Path(__file__).resolve().parents[1] / 'static/assets/flags'
    return frozenset(path.stem.upper() for path in assets.glob('*.svg'))


def is_chess_com_game(raw_pgn: str) -> bool:
    headers = chess.pgn.read_headers(StringIO(raw_pgn)) or {}
    if headers.get('Site', '').strip().lower() == 'chess.com':
        return True
    return any((urlparse(headers.get(header, '')).hostname or '').lower()
               in {'chess.com', 'www.chess.com'} for header in ('Site', 'Link'))


def player_country(username: str) -> str | None:
    """Serialize public API requests and cache successful profiles for 24 hours."""
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_-]{1,64}', username):
        return None
    with _profile_lock:
        now = monotonic()
        cached = _cache.get(username)
        if cached is not None and cached[0] > now:
            _cache.move_to_end(username)
            return cached[1]
        country = None
        failed = False
        try:
            profile = _get_json(f'https://api.chess.com/pub/player/{quote(username, safe="")}',
                                timeout=4, max_size=128_000)
            country_url = profile.get('country') if isinstance(profile, dict) else None
            if isinstance(country_url, str):
                parsed = urlparse(country_url)
                match = re.fullmatch(r'/pub/country/([a-zA-Z]{2})/?', parsed.path)
                if parsed.scheme == 'https' and parsed.netloc.lower() == 'api.chess.com' and match:
                    code = match[1].upper()
                    if code in supported_countries():
                        country = code
        except ValueError:
            failed = True
        _cache[username] = (monotonic() + (300 if failed else 86_400), country)
        _cache.move_to_end(username)
        while len(_cache) > 1024:
            _cache.popitem(last=False)
        return country

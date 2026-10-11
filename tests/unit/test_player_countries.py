from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import player_countries as service
from app.api.routes import games


@pytest.fixture(autouse=True)
def empty_cache():
    service._cache.clear()
    yield
    service._cache.clear()


def test_profile_lookup_is_normalized_cached_and_has_short_timeout(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return {'country': 'https://api.chess.com/pub/country/US'}

    monkeypatch.setattr(service, '_get_json', get)
    assert service.player_country(' Hikaru ') == 'US'
    assert service.player_country('hikaru') == 'US'
    assert len(calls) == 1
    assert calls[0] == ('https://api.chess.com/pub/player/hikaru', {'timeout': 4, 'max_size': 128_000})


@pytest.mark.parametrize('profile', [None, [], {}, {'country': None},
    {'country': 'https://example.com/pub/country/US'},
    {'country': 'https://api.chess.com/pub/country/../../US'},
    {'country': 'https://api.chess.com/pub/country/ZZ'},
])
def test_missing_or_invalid_country_does_not_make_up_a_flag(monkeypatch, profile):
    monkeypatch.setattr(service, '_get_json', lambda *a, **kw: profile)
    assert service.player_country('player') is None


def test_failure_is_temporarily_cached_and_can_recover(monkeypatch):
    clock = [0]
    calls = []
    monkeypatch.setattr(service, 'monotonic', lambda: clock[0])

    def get(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('Unavailable')
        return {'country': 'https://api.chess.com/pub/country/GB'}

    monkeypatch.setattr(service, '_get_json', get)
    assert service.player_country('player') is None
    clock[0] = 299
    assert service.player_country('player') is None
    assert len(calls) == 1
    clock[0] = 301
    assert service.player_country('player') == 'GB'
    assert len(calls) == 2


def test_positive_profiles_expire_after_a_day(monkeypatch):
    clock = [0]
    calls = []
    monkeypatch.setattr(service, 'monotonic', lambda: clock[0])

    def get(*a, **kw):
        calls.append(True)
        return {'country': 'https://api.chess.com/pub/country/US'}

    monkeypatch.setattr(service, '_get_json', get)
    service.player_country('player')
    clock[0] = 86_401
    service.player_country('player')
    assert len(calls) == 2


@pytest.mark.parametrize(('headers', 'expected'), [
    ('[Site "Chess.com"]', True),
    ('[Site "https://www.chess.com/"]', True),
    ('[Site "Local"]\n[Link "https://www.chess.com/game/live/123"]', True),
    ('[Site "Local"]', False),
    ('[Site "https://chess.com.example.com"]', False),
])
def test_generic_pgn_names_are_not_assumed_to_be_chess_com_users(headers, expected):
    assert service.is_chess_com_game(headers + '\n\n1. e4 *') is expected


def test_invalid_username_is_not_requested(monkeypatch):
    monkeypatch.setattr(service, '_get_json', lambda *a, **kw: pytest.fail('Unexpected request'))
    assert service.player_country('../../someone') is None


def test_endpoint_preserves_white_black_assignment_and_ignores_local_games(monkeypatch):
    game = SimpleNamespace(raw_pgn='[Site "Chess.com"]\n\n1. e4 *',
                           white_player='WhitePlayer', black_player='BlackPlayer')
    monkeypatch.setattr(games, 'get_game', lambda *args: game)
    monkeypatch.setattr(games, 'player_country', lambda name: {'WhitePlayer': 'US', 'BlackPlayer': 'GB'}[name])
    result = games.read_player_countries(10, None)
    assert (result.white_country, result.black_country) == ('US', 'GB')
    game.raw_pgn = '[Site "Local"]\n\n1. e4 *'
    monkeypatch.setattr(games, 'player_country', lambda *args: pytest.fail('Unexpected profile lookup'))
    result = games.read_player_countries(10, None)
    assert result.white_country is result.black_country is None
    monkeypatch.setattr(games, 'get_game', lambda *args: None)
    with pytest.raises(HTTPException) as error:
        games.read_player_countries(404, None)
    assert error.value.status_code == 404

import json
import re
from urllib.parse import quote, urlparse

import httpx


CHESS_COM_USER_AGENT = "ChessAnalyzer/0.1"
MAX_CHESS_COM_RESPONSE_SIZE = 20_000_000
GAME_PATHS = (
    re.compile(r"/(?:analysis/)?game/(live|daily)/([0-9]+)"),
    re.compile(r"/(live|daily)/game/([0-9]+)"),
)


def fetch_chess_com_pgn(game_url: str) -> str:
    game_type, game_id = parse_chess_com_url(game_url)
    details = _get_json(
        f"https://www.chess.com/callback/{game_type}/game/{game_id}"
    )
    game = details.get("game", {})
    headers = game.get("pgnHeaders", {})
    username = headers.get("White")
    date = headers.get("UTCDate") or headers.get("Date")

    if not username or not date or not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date):
        raise ValueError("Chess.com did not return the game details")

    year, month, _ = date.split(".")
    archive_url = (
        "https://api.chess.com/pub/player/"
        f"{quote(str(username))}/games/{year}/{month}"
    )
    archive = _get_json(archive_url)

    for game_record in archive.get("games", []):
        record_url = str(game_record.get("url", ""))
        if _game_id_from_url(record_url) == game_id and game_record.get("pgn"):
            return str(game_record["pgn"])

    raise ValueError("PGN was not found for this Chess.com game")


def parse_chess_com_url(game_url: str) -> tuple[str, str]:
    parsed = urlparse(game_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "chess.com" or host.endswith(".chess.com")
    ):
        raise ValueError("Enter a valid https://chess.com game link")

    for pattern in GAME_PATHS:
        match = pattern.search(parsed.path)
        if match:
            return match.group(1), match.group(2)
    raise ValueError("Enter a Chess.com live or daily game link")


def _game_id_from_url(game_url: str) -> str | None:
    match = re.search(r"/(?:live|daily)/([0-9]+)", game_url)
    return match.group(1) if match else None


def _get_json(url: str, *, timeout: float = 15, max_size: int = MAX_CHESS_COM_RESPONSE_SIZE) -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": CHESS_COM_USER_AGENT,
    }
    content = bytearray()
    try:
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_size:
                    raise ValueError("Chess.com response is too large")
    except httpx.HTTPError as error:
        raise ValueError("Could not download this public Chess.com game") from error

    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Chess.com returned an invalid response") from error

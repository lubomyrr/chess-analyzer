from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from kombu.exceptions import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.game import Game
from app.repositories.games import (
    create_game,
    delete_game,
    get_game,
    get_game_for_update,
    get_game_moves,
    get_games,
)
from app.schemas.game import (
    GameAnalysisResponse,
    GameResponse,
    PlayerStatisticsResponse,
)
from app.services.chess_com import fetch_chess_com_pgn
from app.services.game_statistics import calculate_player_statistics
from app.services.pgn_parser import parse_pgn
from app.workers.analyze_game import analyze_game_task


router = APIRouter(prefix="/games", tags=["Games"])

MAX_PGN_SIZE = 1_000_000


@router.post("", response_model=GameResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_game(
    file: Annotated[UploadFile, File(description="One PGN game")],
    user_color: Annotated[Literal["white", "black"], Form()],
    database: Annotated[Session, Depends(get_db)],
) -> GameResponse:
    file_content = await file.read(MAX_PGN_SIZE + 1)

    if len(file_content) > MAX_PGN_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="PGN file is larger than 1 MB",
        )

    try:
        raw_pgn = file_content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PGN file must use UTF-8 encoding",
        ) from error

    return _save_game(raw_pgn, user_color, database)


@router.post(
    "/from-chess-com",
    response_model=GameResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_chess_com_game(
    url: Annotated[str, Form()],
    user_color: Annotated[Literal["white", "black"], Form()],
    database: Annotated[Session, Depends(get_db)],
) -> GameResponse:
    try:
        raw_pgn = fetch_chess_com_pgn(url)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return _save_game(raw_pgn, user_color, database)


@router.post(
    "/{game_id}/analyze",
    response_model=GameResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_game_analysis(
    game_id: int,
    database: Annotated[Session, Depends(get_db)],
) -> GameResponse:
    game = get_game_for_update(database, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status in {"queued", "analyzing"}:
        raise HTTPException(
            status_code=409,
            detail="Game is already queued or being analyzed",
        )

    game.status = "queued"
    game.engine = "stockfish"
    game.error_message = None
    game.analyzed_at = None
    database.commit()

    _queue_analysis(database, game)
    return GameResponse.model_validate(game)


@router.get("", response_model=list[GameResponse])
def list_games(
    database: Annotated[Session, Depends(get_db)],
) -> list[GameResponse]:
    return [GameResponse.model_validate(game) for game in get_games(database)]


@router.get("/{game_id}", response_model=GameResponse)
def read_game(
    game_id: int,
    database: Annotated[Session, Depends(get_db)],
) -> GameResponse:
    game = get_game(database, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameResponse.model_validate(game)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_game(
    game_id: int,
    database: Annotated[Session, Depends(get_db)],
) -> Response:
    game = get_game(database, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    delete_game(database, game)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{game_id}/analysis", response_model=GameAnalysisResponse)
def read_game_analysis(
    game_id: int,
    database: Annotated[Session, Depends(get_db)],
) -> GameAnalysisResponse:
    game = get_game(database, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    moves = get_game_moves(database, game.id)
    return GameAnalysisResponse(
        game_id=game.id,
        status=game.status,
        engine=game.engine,
        white_stats=PlayerStatisticsResponse(
            **calculate_player_statistics(moves, "white", game.white_player)
        ),
        black_stats=PlayerStatisticsResponse(
            **calculate_player_statistics(moves, "black", game.black_player)
        ),
        moves=moves,
    )


def _queue_analysis(database: Session, game: Game) -> None:
    try:
        analyze_game_task.delay(game.id)
    except OperationalError as error:
        game.status = "failed"
        game.error_message = "Analysis queue is unavailable"
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis queue is unavailable",
        ) from error


def _save_game(
    raw_pgn: str,
    user_color: str,
    database: Session,
) -> GameResponse:
    try:
        parsed_game = parse_pgn(raw_pgn)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    game = create_game(
        database=database,
        parsed_game=parsed_game,
        raw_pgn=raw_pgn,
        user_color=user_color,
    )
    _queue_analysis(database, game)
    return GameResponse.model_validate(game)

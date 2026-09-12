from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.games import router as games_router
from app.api.routes.health import router as health_router


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Chess Analyzer",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(games_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

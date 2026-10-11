from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.games import router as games_router
from app.api.routes.health import router as health_router
from app.services.position_candidates import close_candidate_engine


STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        close_candidate_engine()


app = FastAPI(
    title="Chess Analyzer",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(games_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

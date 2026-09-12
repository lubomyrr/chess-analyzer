from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(
    database: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    database.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}

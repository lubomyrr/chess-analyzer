import logging
import os
import subprocess
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.core.config import settings


def wait_for_database(timeout: float = 120, retry_interval: float = 2) -> None:
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                return
            except OperationalError:
                if time.monotonic() >= deadline:
                    raise
                logging.warning("Database is not ready; retrying in %.0f seconds", retry_interval)
                time.sleep(retry_interval)
    finally:
        engine.dispose()


def main() -> None:
    wait_for_database()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    os.execvp(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000",
    ])


if __name__ == "__main__":
    main()
